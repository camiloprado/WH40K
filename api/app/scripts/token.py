import hashlib
import secrets
from pathlib import Path

from app.config import get_settings
from app.db import session_factory
from app.security import invalidate_all


def main() -> None:
    token = secrets.token_urlsafe(48)
    digest = hashlib.sha256(token.encode()).hexdigest()
    path = Path(get_settings().token_hash_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(digest, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    try:
        db = session_factory()()
        invalidate_all(db)
        db.commit()
        db.close()
    except Exception as exc:
        print(f"sessões não invalidadas: {exc.__class__.__name__}")
    print(token)


if __name__ == "__main__":
    main()
