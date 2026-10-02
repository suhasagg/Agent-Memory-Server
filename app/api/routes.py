from uuid import UUID
from fastapi import APIRouter,Depends,Header,HTTPException
from app.core.config import settings
from app.domain.models import MemoryWrite,RecallRequest
from app.services.memory import MemoryService
router=APIRouter(); svc=MemoryService()
def auth(x_api_key:str=Header(...)):
 if x_api_key!=settings.api_key: raise HTTPException(401,'invalid api key')
@router.post('/v1/memories',dependencies=[Depends(auth)])
async def remember(w:MemoryWrite): return await svc.remember(w)
@router.post('/v1/recall',dependencies=[Depends(auth)])
async def recall(r:RecallRequest): return await svc.recall(r)
@router.delete('/v1/memories/{memory_id}',status_code=204,dependencies=[Depends(auth)])
async def delete(memory_id:UUID,tenant_id:str): await svc.pg.delete(tenant_id,memory_id)
@router.get('/healthz')
async def health(): return {'status':'ok'}
