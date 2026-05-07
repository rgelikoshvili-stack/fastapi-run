import os

from fastapi import APIRouter

from app.api.response_utils import ok_response

router = APIRouter(tags=["version"])


@router.get("/version")
def get_version():
    return ok_response(
        "Version",
        {
            "app": "Bridge Hub",
            "commit_sha": os.environ.get("COMMIT_SHA") or "unknown",
            "build_time": os.environ.get("BUILD_TIME") or "unknown",
            "environment": os.environ.get("ENVIRONMENT") or "development",
        },
    )
