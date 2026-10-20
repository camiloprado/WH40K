from fastapi import HTTPException


def err(status: int, code: str, detail: str, errors: list | None = None) -> None:
    var_dctBody: dict = {"detail": detail, "code": code}
    if errors is not None:
        var_dctBody["errors"] = errors
    raise HTTPException(status_code=status, detail=var_dctBody)
