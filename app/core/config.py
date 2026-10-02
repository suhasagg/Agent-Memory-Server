from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    service_name: str='agent-memory-server'
    database_url: str='postgresql+asyncpg://memory:memory@postgres:5432/memory'
    redis_url: str='redis://redis:6379/0'
    embedding_url: str|None=None
    embedding_dim: int=384
    working_ttl_seconds: int=86400
    max_recall: int=50
    api_key: str='dev-change-me'
settings=Settings()
