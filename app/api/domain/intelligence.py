"""Domain: Intelligence — AI chat, classification, learning, patterns, transaction AI."""
from fastapi import APIRouter
from app.api import (
    routes_ai_chat,
    routes_ai_journal,
    routes_ai_recommend,
    routes_chat,
    routes_claude_chat,
    routes_transaction_ai,
    routes_transaction_memory,
    routes_learning,
    routes_learning_explain,
    routes_patterns,
    routes_decision_engine,
    routes_qa,
)

router = APIRouter(tags=["intelligence"])
router.include_router(routes_ai_chat.router)
router.include_router(routes_ai_journal.router)
router.include_router(routes_ai_recommend.router)
router.include_router(routes_chat.router)
router.include_router(routes_claude_chat.router)
router.include_router(routes_transaction_ai.router)
router.include_router(routes_transaction_memory.router)
router.include_router(routes_learning.router)
router.include_router(routes_learning_explain.router)
router.include_router(routes_patterns.router)
router.include_router(routes_decision_engine.router)
router.include_router(routes_qa.router)
