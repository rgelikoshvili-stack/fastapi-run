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
