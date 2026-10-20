from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

HEAD_REVISION = "0015_db2_db6"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://wh40k:wh40k@127.0.0.1:15432/wh40k"
    app_token_hash: str = ""
    extra_hosts: str = ""
    token_hash_file: str = "data/app_token_hash"
    backup_dir: str = "backups"
    bsdata_cache_dir: str = "data/bsdata"


@lru_cache
def get_settings() -> Settings:
    return Settings()
