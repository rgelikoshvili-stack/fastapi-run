from fastapi import APIRouter
import os

router = APIRouter()

@router.get("/version")
def get_version():
    return {
        "ok": True,
        "version": os.getenv("APP_VERSION", "0.1.0"),
        "build": os.getenv("APP_BUILD", "local"),
        "environment": os.getenv("APP_ENV", "dev"),
    }