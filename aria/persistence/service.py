import os
from pathlib import Path
from .repositories import InMemoryEventStore,PostgresEventStore
from .writer import MemoryWriter,DurableWriter,Limits

def create_history(default_directory):
    mode=os.environ.get('ARIA_HISTORY_BACKEND','memory')  # explicit development default, never an outage fallback
    if mode=='memory':return MemoryWriter(InMemoryEventStore())
    if mode!='postgres':raise ValueError('ARIA_HISTORY_BACKEND must be memory or postgres')
    dsn=os.environ.get('ARIA_HISTORY_DSN')
    if not dsn:raise ValueError('PostgreSQL history selected but ARIA_HISTORY_DSN missing')
    return DurableWriter(PostgresEventStore(dsn),Path(os.environ.get('ARIA_HISTORY_SPOOL',str(default_directory/'history-spool'))),Limits.environment())
