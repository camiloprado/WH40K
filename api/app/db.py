from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import HEAD_REVISION, get_settings

_engine = None
_factory = None


def get_engine():
    global _engine, _factory
    url = get_settings().database_url
    if _engine is None or str(_engine.url) != url:
        _engine = create_engine(url, pool_size=5, max_overflow=0, pool_pre_ping=True)
        _factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _factory is not None
    return _factory


def db_session() -> Iterator[Session]:
    db = session_factory()()
    try:
        ensure_head(db)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_head(db: Session) -> None:
    from app.errors import err

    try:
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:
        db.rollback()
        err(503, "db_not_at_head", f"Banco indisponível: {exc.__class__.__name__}")
    if rev != HEAD_REVISION:
        err(503, "db_not_at_head", "Banco fora do head")
