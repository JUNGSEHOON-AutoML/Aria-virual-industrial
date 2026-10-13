"""Exact float32 cosine search. No approximate index or implicit score clipping."""
import numpy as np


def normalized(x):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError('Expected finite feature matrix')
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError('Zero feature cannot define cosine similarity')
    return np.ascontiguousarray(x / norms)


class NumpyExact:
    def __init__(self, bank, query_chunk=256, bank_chunk=4096):
        self.bank = normalized(bank)
        self.query_chunk, self.bank_chunk = query_chunk, bank_chunk

    def __call__(self, query):
        query = normalized(query); scores=[]; indices=[]
        for start in range(0, len(query), self.query_chunk):
            q=query[start:start+self.query_chunk]
            best=np.full(len(q),-np.inf,dtype=np.float32); ix=np.zeros(len(q),dtype=np.int64)
            for b in range(0,len(self.bank),self.bank_chunk):
                dot=q @ self.bank[b:b+self.bank_chunk].T
                local=dot.argmax(1); v=dot[np.arange(len(q)),local]; take=v>best
                best[take]=v[take];ix[take]=b+local[take]
            scores.append(1-best); indices.append(ix)
        return np.concatenate(scores),np.concatenate(indices)


class TorchExact:
    def __init__(self, bank, query_chunk=256, bank_chunk=4096):
        import torch
        self.torch=torch
        torch.backends.cuda.matmul.allow_tf32=False
        torch.set_float32_matmul_precision('highest')
        self.bank=torch.as_tensor(normalized(bank),device='cuda:0')
        self.query_chunk,self.bank_chunk=query_chunk,bank_chunk

    def __call__(self, query):
        t=self.torch; q=t.as_tensor(normalized(query),device='cuda:0'); scores=[];indices=[]
        with t.no_grad():
            for a in q.split(self.query_chunk):
                best=t.full((len(a),),-float('inf'),device=a.device);ix=t.zeros(len(a),dtype=t.int64,device=a.device)
                for b in range(0,len(self.bank),self.bank_chunk):
                    v,i=(a @ self.bank[b:b+self.bank_chunk].T).max(1);take=v>best
                    best=t.where(take,v,best);ix=t.where(take,i+b,ix)
                scores.append((1-best).cpu().numpy());indices.append(ix.cpu().numpy())
        return np.concatenate(scores),np.concatenate(indices)


class FaissExact:
    def __init__(self, bank):
        import faiss
        self.faiss=faiss; self.resources=faiss.StandardGpuResources()
        self.resources.setTempMemory(128*1024*1024)
        cpu=faiss.IndexFlatIP(bank.shape[1])
        options=faiss.GpuClonerOptions();options.useFloat16=False
        self.index=faiss.index_cpu_to_gpu(self.resources,0,cpu,options)
        self.index.add(normalized(bank))

    def __call__(self, query):
        scores,indices=self.index.search(normalized(query),1)
        return 1-scores[:,0],indices[:,0]


def parity(reference, candidate, queries, threshold=None):
    max_error=0.; changed=0; ties=0; images=0
    for query in queries:
        a,ai=reference(query);b,bi=candidate(query)
        error=float(np.max(np.abs(a-b)))
        if not np.isfinite(error):raise ValueError('Non-finite exact-search difference')
        max_error=max(max_error,error);ties+=int(np.sum(ai!=bi));images+=1
        if threshold is not None:changed+=int((a.max()>threshold)!=(b.max()>threshold))
    return dict(passed=max_error<=1e-5 and changed==0,max_absolute_score_error=max_error,
                verdict_changes=changed,nearest_index_disagreements=ties,images=images,
                tolerance=1e-5,threshold=threshold)
