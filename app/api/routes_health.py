from fastapi import APIRouter
from datetime import datetime
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")
def health_check():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()

        return ok_response(
            "Health check OK",
            {
                "service": "Bridge Hub",
                "version": "1.0.0",
                "environment": "production",
                "db": "connected",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        return error_response("Health check failed", "HEALTH_ERROR", str(e))
