from fastapi import HTTPException


def api_error(status: int, code: str, message: str, **extra) -> HTTPException:
    """Errors always carry a stable machine code and a human message; never internals."""
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def not_found(what: str = "Item") -> HTTPException:
    # Same response for "does not exist" and "belongs to someone else", so IDs cannot be probed.
    return api_error(404, "NOT_FOUND", f"{what} not found.")
