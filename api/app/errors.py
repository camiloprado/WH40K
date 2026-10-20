from fastapi import HTTPException


def err(status: int, code: str, detail: str, errors: list | None = None) -> None:
    body: dict = {"detail": detail, "code": code}
    if errors is not None:
        body["errors"] = errors
    raise HTTPException(status_code=status, detail=body)
