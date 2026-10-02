import json
from uuid import UUID
from sqlalchemy import text
from app.core.db import Session
from app.domain.models import MemoryRecord, MemoryKind
class PostgresMemoryRepository:
 async def put(self,m:MemoryRecord,embedding:list[float]|None=None):
  async with Session.begin() as s:
   q=text('''INSERT INTO memories(id,tenant_id,agent_id,user_id,kind,namespace,content,importance,metadata,idempotency_key,embedding,version)
   VALUES(:id,:t,:a,:u,:k,:n,:c,:i,CAST(:md AS jsonb),:ik,CAST(:e AS vector),:v)
   ON CONFLICT (tenant_id,idempotency_key) WHERE idempotency_key IS NOT NULL DO UPDATE SET content=EXCLUDED.content,metadata=EXCLUDED.metadata,version=memories.version+1 RETURNING id''')
   await s.execute(q,dict(id=str(m.id),t=m.tenant_id,a=m.agent_id,u=m.user_id,k=m.kind.value,n=m.namespace,c=m.content,i=m.importance,md=json.dumps(m.metadata),ik=m.idempotency_key,e=str(embedding) if embedding else None,v=m.version))
  return m
 async def semantic(self,tenant,agent,namespace,embedding,limit,kinds):
  async with Session() as s:
   rows=(await s.execute(text('''SELECT *, 1-(embedding <=> CAST(:e AS vector)) AS score FROM memories
    WHERE tenant_id=:t AND agent_id=:a AND namespace=:n AND kind = ANY(:k) AND embedding IS NOT NULL AND deleted_at IS NULL
    ORDER BY embedding <=> CAST(:e AS vector) LIMIT :l'''),dict(e=str(embedding),t=tenant,a=agent,n=namespace,k=[x.value for x in kinds],l=limit))).mappings().all()
   return rows
 async def delete(self,tenant:str,mid:UUID):
  async with Session.begin() as s: await s.execute(text('UPDATE memories SET deleted_at=now() WHERE tenant_id=:t AND id=:i'),{'t':tenant,'i':str(mid)})
