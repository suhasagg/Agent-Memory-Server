from enum import StrEnum
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
class MemoryKind(StrEnum):
    WORKING='working'; EPISODIC='episodic'; SEMANTIC='semantic'; PROCEDURAL='procedural'
class MemoryWrite(BaseModel):
    tenant_id:str; agent_id:str; user_id:str|None=None; kind:MemoryKind
    content:str=Field(min_length=1,max_length=100000); namespace:str='default'
    importance:float=Field(default=.5,ge=0,le=1); metadata:dict={}; idempotency_key:str|None=None
class MemoryRecord(MemoryWrite):
    id:UUID=Field(default_factory=uuid4); created_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc)); version:int=1
class RecallRequest(BaseModel):
    tenant_id:str; agent_id:str; query:str; kinds:list[MemoryKind]=list(MemoryKind); namespace:str='default'; limit:int=10
class RecallHit(BaseModel):
    memory:MemoryRecord; score:float; reasons:list[str]=[]
