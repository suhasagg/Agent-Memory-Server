import json
from redis.asyncio import Redis
from app.core.config import settings
from app.domain.models import MemoryRecord
class WorkingMemoryRepository:
 def __init__(self): self.r=Redis.from_url(settings.redis_url,decode_responses=True)
 def key(self,m): return f'wm:{m.tenant_id}:{m.agent_id}:{m.namespace}:{m.id}'
 async def put(self,m:MemoryRecord):
  await self.r.set(self.key(m),m.model_dump_json(),ex=settings.working_ttl_seconds); return m
 async def list(self,tenant,agent,namespace,limit=50):
  out=[]
  async for key in self.r.scan_iter(f'wm:{tenant}:{agent}:{namespace}:*',count=100):
   if len(out)>=limit: break
   if v:=await self.r.get(key): out.append(MemoryRecord.model_validate_json(v))
  return out
