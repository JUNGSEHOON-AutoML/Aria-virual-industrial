"""Durable local SQLite WAL spool; PostgreSQL is written by one background thread.

submit ACK means local FULL-synchronous commit, never a PostgreSQL ACK.
The durable spool IS the bounded persistence queue: no volatile event hand-off.
SQLite handles WAL checksums/atomic recovery; SHA-256 detects record corruption.
One writer process holds an advisory file lock for its entire spool lifetime.
"""
import fcntl
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from .contracts import canonical,digest,PersistenceFault

@dataclass(frozen=True)
class Limits:
    queue_size:int=4096
    spool_bytes:int=64*1024*1024
    retry_min:float=.2
    retry_max:float=5.
    max_lag:float=300.
    batch_size:int=64
    shutdown_timeout:float=8.
    def __post_init__(self):
        if min(self.queue_size,self.spool_bytes,self.retry_min,self.max_lag,self.batch_size,self.shutdown_timeout)<=0 or self.retry_max<self.retry_min:raise ValueError('Invalid persistence limits')
    @classmethod
    def environment(cls):
        names={'queue_size':int,'spool_bytes':int,'retry_min':float,'retry_max':float,'max_lag':float,'batch_size':int,'shutdown_timeout':float}
        return cls(**{k:t(os.environ['ARIA_HISTORY_'+k.upper()]) for k,t in names.items() if 'ARIA_HISTORY_'+k.upper() in os.environ})

class DurableWriter:
    def __init__(self,store,directory,limits=None):
        self.store=store;self.limits=limits or Limits();self.path=Path(directory);self.path.mkdir(parents=True,exist_ok=True)
        self.file_lock=(self.path/'writer.lock').open('a+b')
        try:fcntl.flock(self.file_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:self.file_lock.close();raise PersistenceFault('Spool already owned by another process') from exc
        self.lock=threading.RLock();self.wake=threading.Event();self.stop=threading.Event();self.accepting=True
        self.db=sqlite3.connect(self.path/'spool.sqlite3',check_same_thread=False)
        self.db.execute('PRAGMA auto_vacuum=INCREMENTAL');self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS contexts(run_id TEXT PRIMARY KEY,body TEXT NOT NULL,hash TEXT NOT NULL); CREATE TABLE IF NOT EXISTS pending(id INTEGER PRIMARY KEY,run_id TEXT NOT NULL,sequence INTEGER NOT NULL,body TEXT NOT NULL,hash TEXT NOT NULL,enqueued REAL NOT NULL,UNIQUE(run_id,sequence)); CREATE TABLE IF NOT EXISTS checkpoints(run_id TEXT PRIMARY KEY,enqueued INTEGER NOT NULL DEFAULT 0,persisted INTEGER NOT NULL DEFAULT 0);')
        if self.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise PersistenceFault('Spool corruption; preserve files for recovery')
        self.retry_count=0;self.last_error=None;self.status='RECOVERING' if self._count() else 'HEALTHY';self.failed_event=None
        self.thread=threading.Thread(target=self._loop,name='aria-event-writer',daemon=True);self.thread.start()
    def _count(self):return self.db.execute('SELECT count(*) FROM pending').fetchone()[0]
    def register(self,context):
        with self.lock,self.db:
            body=canonical(context);h=digest(context);row=self.db.execute('SELECT hash FROM contexts WHERE run_id=?',(context['run_id'],)).fetchone()
            if row and row[0]!=h:raise PersistenceFault('Run context changed')
            if not row and self.disk_bytes()+len(body.encode())+16384>self.limits.spool_bytes:raise PersistenceFault('Spool context disk budget exceeded')
            self.db.execute('INSERT OR IGNORE INTO contexts VALUES(?,?,?)',(context['run_id'],body,h))
            self.db.execute('INSERT OR IGNORE INTO checkpoints(run_id) VALUES(?)',(context['run_id'],))
    def disk_bytes(self):return sum(p.stat().st_size for p in self.path.glob('spool.sqlite3*') if p.is_file())
    def can_advance(self):
        with self.lock:
            if not self.accepting:raise PersistenceFault('Writer closed to new work')
            if self.failed_event:raise PersistenceFault('Uncommitted event retained in memory; persistence failure requires intervention')
            if self.status=='FAULT':raise PersistenceFault(self.last_error or 'Spool failure')
            n,oldest=self.db.execute('SELECT count(*),min(enqueued) FROM pending').fetchone()
            if n>=self.limits.queue_size:
                self.status='BACKPRESSURE';self.last_error='Persistence queue full; pause required';raise PersistenceFault(self.last_error)
            if oldest and time.time()-oldest>self.limits.max_lag:
                self.status='BACKPRESSURE';self.last_error='Maximum persistence lag exceeded; pause required';raise PersistenceFault(self.last_error)
    def submit(self,event):
        with self.lock:
            try:
                self.can_advance();body=canonical(event);h=digest(event)
                existing=self.db.execute('SELECT hash FROM pending WHERE run_id=? AND sequence=?',(event['run_id'],event['sequence'])).fetchone()
                if existing:
                    if existing[0]!=h:raise PersistenceFault('Spool identity collision')
                    return
                if self.disk_bytes()+len(body.encode())+16384>self.limits.spool_bytes:raise PersistenceFault('Spool disk budget exceeded')
                with self.db:
                    self.db.execute('INSERT INTO pending(run_id,sequence,body,hash,enqueued) VALUES(?,?,?,?,?)',(event['run_id'],event['sequence'],body,h,time.time()))
                    self.db.execute('UPDATE checkpoints SET enqueued=max(enqueued,?) WHERE run_id=?',(event['sequence'],event['run_id']))
                self.wake.set()
            except Exception as exc:
                self.status='FAULT';self.last_error=str(exc);self.failed_event=event
                raise PersistenceFault('Durable append failed: '+str(exc)) from exc
    def _batch(self):
        with self.lock:
            rows=self.db.execute('SELECT id,body,hash FROM pending ORDER BY id LIMIT ?',(self.limits.batch_size,)).fetchall();events=[];contexts={}
            for id,body,h in rows:
                e=json.loads(body)
                if digest(e)!=h:raise PersistenceFault('Spool event checksum mismatch at '+str(id))
                events.append(e)
                if e['run_id'] not in contexts:
                    row=self.db.execute('SELECT body,hash FROM contexts WHERE run_id=?',(e['run_id'],)).fetchone()
                    if not row:raise PersistenceFault('Missing spool run context')
                    ctx=json.loads(row[0])
                    if digest(ctx)!=row[1]:raise PersistenceFault('Spool context checksum mismatch')
                    contexts[e['run_id']]=ctx
            return rows,events,contexts
    def _loop(self):
        delay=self.limits.retry_min
        while not self.stop.is_set():
            try:
                rows,events,contexts=self._batch()
                if not rows:self.wake.wait(.1);self.wake.clear();continue
                self.store.append(events,contexts)
                with self.lock:
                    with self.db:
                        for row,e in zip(rows,events):
                            self.db.execute('DELETE FROM pending WHERE id=?',(row[0],))
                            self.db.execute('UPDATE checkpoints SET persisted=max(persisted,?) WHERE run_id=?',(e['sequence'],e['run_id']))
                    self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)');self.db.execute('PRAGMA incremental_vacuum(64)')
                    if self.status!='FAULT':self.status='HEALTHY';self.last_error=None
                delay=self.limits.retry_min
            except PersistenceFault as exc:
                with self.lock:self.status='FAULT';self.last_error=str(exc)
                self.stop.wait(.2)  # Preserve corrupt records; operator recovery required.
            except Exception as exc:
                with self.lock:
                    if self.status!='FAULT':self.status='DEGRADED'
                    self.retry_count+=1;self.last_error=str(exc)[:500]
                self.stop.wait(delay);delay=min(delay*2,self.limits.retry_max)
    def health(self):
        with self.lock:
            n,oldest=self.db.execute('SELECT count(*),min(enqueued) FROM pending').fetchone()
            checkpoints={r:dict(last_enqueued_sequence=e,last_persisted_sequence=p) for r,e,p in self.db.execute('SELECT * FROM checkpoints')}
            return dict(mode=self.store.mode,persistence_status=self.status,queue_depth=n,spool_bytes=self.disk_bytes(),retry_count=self.retry_count,last_error=self.last_error,lag_s=max(0,time.time()-oldest) if oldest else 0,checkpoints=checkpoints,failed_event_id=self.failed_event.get('event_id') if self.failed_event else None,limits=self.limits.__dict__)
    def flush(self,timeout=8):
        end=time.monotonic()+timeout;self.wake.set()
        while time.monotonic()<end:
            with self.lock:
                if not self._count():return True
            time.sleep(.02)
        return False
    def close(self):
        with self.lock:self.accepting=False
        flushed=self.flush(self.limits.shutdown_timeout);self.stop.set();self.wake.set();self.thread.join(8)
        if self.thread.is_alive():raise PersistenceFault('Writer did not stop; spool retained and lock held')
        with self.lock:self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)');self.db.close();self.store.close();self.file_lock.close()
        if self.failed_event:raise PersistenceFault('Shutdown contains an uncommitted event: '+self.failed_event['event_id'])
        return flushed

class MemoryWriter:
    def __init__(self,store):self.store=store;self.contexts={};self.accepting=True
    def register(self,context):self.contexts[context['run_id']]=context
    def submit(self,event):self.can_advance();self.store.append([event],{event['run_id']:self.contexts[event['run_id']]})
    def can_advance(self):
        if not self.accepting:raise PersistenceFault('Writer closed')
    def health(self):return dict(mode='memory',persistence_status='VOLATILE_DEVELOPMENT',queue_depth=0)
    def flush(self,timeout=8):return True
    def close(self):self.accepting=False;self.store.close();return True
