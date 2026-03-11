"""Natural Language Query API routes.

Conversational interface for querying betting data. Inspired by Gambly
and Action Network Playbook AI.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from sba.services.nlq import query

from sba.web.errors import safe_endpoint

router = APIRouter(tags=["nlq"])


class NLQRequest(BaseModel):
    question: str


@router.post("/ask")
@safe_endpoint
def api_ask(req: NLQRequest):
    """Ask a natural language question about your betting data.

    Examples:
    - "How did I do this week?"
    - "What's my best market?"
    - "Am I profitable at DraftKings?"
    - "Show my win rate"
    """
    return query(req.question)
