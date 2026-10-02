import hashlib, math
from app.core.config import settings
class EmbeddingService:
 async def embed(self,text:str)->list[float]:
  # Deterministic local fallback so the service runs without a model provider.
  # Replace through an adapter in production; never hash-embed for semantic quality.
  d=settings.embedding_dim; v=[0.0]*d
  for token in text.lower().split():
   h=hashlib.sha256(token.encode()).digest(); idx=int.from_bytes(h[:4],'big')%d; v[idx]+=1 if h[4]&1 else -1
  norm=math.sqrt(sum(x*x for x in v)) or 1
  return [x/norm for x in v]
