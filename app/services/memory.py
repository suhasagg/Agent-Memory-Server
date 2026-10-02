from app.domain.models import *
from app.repositories.postgres import PostgresMemoryRepository
from app.repositories.working import WorkingMemoryRepository
from app.services.embedding import EmbeddingService
class MemoryService:
 def __init__(self): self.pg=PostgresMemoryRepository(); self.wm=WorkingMemoryRepository(); self.emb=EmbeddingService()
 async def remember(self,w:MemoryWrite):
  m=MemoryRecord(**w.model_dump())
  if m.kind==MemoryKind.WORKING: return await self.wm.put(m)
  return await self.pg.put(m,await self.emb.embed(m.content))
 async def recall(self,r:RecallRequest):
  hits=[]
  if MemoryKind.WORKING in r.kinds:
   for m in await self.wm.list(r.tenant_id,r.agent_id,r.namespace,r.limit):
    q=set(r.query.lower().split()); c=set(m.content.lower().split()); score=len(q&c)/max(1,len(q)); hits.append(RecallHit(memory=m,score=score,reasons=['working-memory lexical match']))
  durable=[k for k in r.kinds if k!=MemoryKind.WORKING]
  if durable:
   rows=await self.pg.semantic(r.tenant_id,r.agent_id,r.namespace,await self.emb.embed(r.query),r.limit,durable)
   for x in rows:
    m=MemoryRecord(id=x['id'],tenant_id=x['tenant_id'],agent_id=x['agent_id'],user_id=x['user_id'],kind=x['kind'],namespace=x['namespace'],content=x['content'],importance=x['importance'],metadata=x['metadata'],idempotency_key=x['idempotency_key'],created_at=x['created_at'],version=x['version'])
    # blended relevance: vector similarity + importance + recency hook
    score=max(0,float(x['score']))*.75+m.importance*.25
    hits.append(RecallHit(memory=m,score=score,reasons=['semantic similarity','importance']))
  return sorted(hits,key=lambda h:h.score,reverse=True)[:r.limit]
