import os
from fastapi import APIRouter, Response

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "templates", "dashboard.html"
)

@router.get("/", response_class=Response)
async def dashboard():
    try:
        with open(TEMPLATE_PATH, encoding="utf-8") as f:
            html = f.read()
        return Response(content=html, media_type="text/html")
    except FileNotFoundError:
        return Response(
            content=f"<h2>Not found: {os.path.abspath(TEMPLATE_PATH)}</h2>",
            media_type="text/html",
            status_code=500,
        )