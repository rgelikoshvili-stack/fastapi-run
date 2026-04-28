from fastapi.responses import JSONResponse


def ok_response(message: str, data=None):
    return {
        "ok": True,
        "message": message,
        "data": data,
        "error": None,
    }


def error_response(message: str, code: str = "ERROR", details=None):
    return {
        "ok": False,
        "message": message,
        "data": None,
        "error": {
            "code": code,
            "details": details,
        },
    }


def http_error(status_code: int, message: str, code: str = "ERROR", details=None) -> JSONResponse:
    """Return a JSONResponse with an error body and the given HTTP status code."""
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "message": message,
            "data": None,
            "error": {"code": code, "details": details},
        },
    )
