import os
from pathlib import Path

import psycopg

SERVER = os.environ.get("TEST_DB_SERVER", "postgresql://wh40k:wh40k@127.0.0.1:15432")
TEST_DB = "wh40k_test"

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"postgresql+psycopg://{SERVER.split('://', 1)[1]}/{TEST_DB}"


def pytest_sessionstart(session) -> None:
    with psycopg.connect(f"{SERVER}/wh40k", autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(config, "head")
