"""
POST /v1/assistant/ask — LLM generation for the member "Ask BEACON" screen.

WHY THIS IS A SERVER ENDPOINT AND NOT A FETCH FROM THE BROWSER
The API key must never reach the client. Vite inlines every VITE_* env var into
the shipped JS bundle, and this repo is public — a key in the frontend is a key
anyone can lift out of devtools on the deployed site. So the key lives here, in
a Container App secret, and the browser only ever talks to us.

WHAT THIS DOES AND DOESN'T CHANGE ABOUT THE HONESTY STORY
Assistant.tsx already does the retrieval half for real: it pulls live
GET /v1/hotspots/geo data and cites the actual suburbs. This endpoint replaces
only the generation half (the old string-template composeAnswer). The facts in
the prompt are the real retrieved rows — the model is told to answer ONLY from
them and to say so when they don't cover the question, so it summarises real
data rather than recalling anything of its own.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

AIMLAPI_URL = "https://api.aimlapi.com/v1/chat/completions"
MODEL = os.getenv("ASSISTANT_MODEL", "deepseek/deepseek-v4-flash")

SYSTEM_PROMPT = (
    "You are BEACON's assistant — a helpful, conversational safety companion for "
    "a South African insurance member. Chat naturally: greetings, general safety "
    "advice, and small talk are all fine, not just data lookups.\n"
    "A DATA block of real historical crime-report figures may be attached below. "
    "When you use a specific number, suburb name, or statistic, it MUST come from "
    "that DATA — never invent a figure. If someone asks about an area or figure "
    "the DATA doesn't cover, say so plainly rather than guessing, then still help "
    "however you can (general advice, asking a clarifying question, etc).\n"
    "This is historical pattern data, NOT a prediction of tonight — never imply "
    "forecasting, and never tell someone a place is 'safe'.\n"
    "Keep replies short and conversational. Never identify or speculate about "
    "individuals."
)


class AskReq(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    # The rows Assistant.tsx already retrieved and is citing on screen. Passed in
    # rather than re-queried so the answer is grounded in exactly what the user
    # can see cited, with no chance of the two drifting apart.
    context: str = Field("", max_length=6000)


class AskRes(BaseModel):
    answer: str
    model: str
    grounded: bool


@router.post("/assistant/ask", response_model=AskRes)
async def ask(body: AskReq) -> AskRes:
    key = os.getenv("AIMLAPI_KEY")
    if not key:
        # 503 rather than a fabricated answer: the client falls back to its own
        # template composer, which is real (if plainer) — never a fake LLM reply.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assistant model not configured on this server.",
        )

    import httpx

    user_content = (
        (f"DATA:\n{body.context}\n\n" if body.context else "")
        + f"QUESTION: {body.question}"
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                AIMLAPI_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "max_tokens": 300,
                    "temperature": 0.2,
                },
            )
        r.raise_for_status()
        payload = r.json()
        answer = (payload["choices"][0]["message"]["content"] or "").strip()
        if not answer:
            raise ValueError("empty completion")
    except Exception as exc:
        logger.warning("assistant upstream failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Assistant model unavailable: {type(exc).__name__}",
        )

    return AskRes(answer=answer, model=MODEL, grounded=bool(body.context))
