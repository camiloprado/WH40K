from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

HEAD_REVISION = "0013_shadow_phase"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://wh40k:wh40k@127.0.0.1:15432/wh40k"
    app_token_hash: str = ""
    extra_hosts: str = ""
    token_hash_file: str = "data/app_token_hash"
    bsdata_cache_dir: str = "data/bsdata"


@lru_cache
def get_settings() -> Settings:
    return Settings()
