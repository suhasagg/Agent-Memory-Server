from app.domain.models import MemoryWrite,MemoryKind
def test_memory_validation():
 m=MemoryWrite(tenant_id='t',agent_id='a',kind=MemoryKind.EPISODIC,content='deployed release 42')
 assert m.importance==.5
