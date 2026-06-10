"""
Demo routes (B-1 step 2) — the public showcase of the agentic flow.

  GET  /demo        -> HTML page: question box + example chips + result area
  POST /demo/ask    -> runs the Gemini function-calling agent, returns JSON
                       { answer, tool_calls, spots[] }

The page shows a "fake" staged loading (rotating step messages) while the
single /demo/ask request runs to completion, then renders the full result:
Gemini's answer, the tool-call log (proof Gemini hit OUR MCP tools), and place
cards with prices + kkday buttons + a /p/{id} link.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.demo.agent import run_demo_agent
from app.demo.page import render_demo_page

router = APIRouter(tags=["demo"])


class AskBody(BaseModel):
    question: str
    lang: str = "auto"


@router.get("/demo", response_class=HTMLResponse)
async def demo_page() -> HTMLResponse:
    return HTMLResponse(content=render_demo_page())


@router.post("/demo/ask")
async def demo_ask(body: AskBody) -> JSONResponse:
    question = (body.question or "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "질문을 입력하세요."})
    try:
        # lang: "auto" | "ko" | "en" | "ja". "auto" lets the agent match the
        # question's language; explicit values pin the toggle choice.
        result = await run_demo_agent(question, lang=body.lang or "auto")
        return JSONResponse(content=result)
    except RuntimeError as e:
        # Config problems (missing key/package) → clear message for the UI.
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": f"처리 중 오류: {e}"})
