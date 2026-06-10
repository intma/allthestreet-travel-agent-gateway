"""
B-1 1단계 검증 (v3) — Gemini가 우리 원격 MCP 도구를 실제로 호출하는지 확인.

왜 v3인가:
  google-genai SDK는 generate_content에서 config를 deepcopy(model_copy(deep=True))
  한다. config.tools 안에 MCP '세션 객체'(FastMCP든 표준 SDK든)가 들어가면 그 안의
  asyncio.Future를 복사 못 해 터진다 (cannot pickle '_asyncio.Future').
  -> 세션을 config에 넣지 않는다. 대신:
     1) MCP에서 도구 목록(스키마)을 받아 '함수 선언(JSON)'으로만 config에 전달
        (순수 데이터라 deepcopy OK)
     2) Gemini가 함수콜을 반환하면 -> 우리가 직접 MCP 세션으로 그 도구를 실행
     3) 도구 결과를 Gemini에 되돌려 최종 답변 생성
  이 수동 오케스트레이션은 SDK 버전에 안 흔들리고, 이후 B-2/B-3에서 카드·구매링크로
  결과를 가공할 때도 우리가 데이터를 손에 쥐므로 유리하다.

준비:
  pip install --upgrade google-genai mcp
  $env:GEMINI_API_KEY="..."   (PowerShell)

실행:
  py demo/gemini_mcp_demo.py
  py demo/gemini_mcp_demo.py "부산 해운대 가볼만한 곳 알려줘"
"""

import asyncio
import json
import os
import sys

from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


MCP_URL = os.getenv(
    "GATEWAY_MCP_URL",
    "https://YOUR-SERVICE.run.app/mcp/",  # set GATEWAY_MCP_URL to your deployed gateway
)
DEFAULT_QUESTION = "부산 해운대 근처 가볼만한 곳과 예약 가능한 티켓이 있으면 알려줘."
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
MAX_TURNS = 8  # 함수콜 -> 실행 -> 재요청 루프 상한


def _clean_schema(node):
    """MCP inputSchema(JSON Schema)를 Gemini function_declarations용으로 정리.
    Gemini가 거부하는 키($schema, additionalProperties, title 등)를 제거."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in ("$schema", "additionalProperties", "title", "default"):
                continue
            out[k] = _clean_schema(v)
        return out
    if isinstance(node, list):
        return [_clean_schema(x) for x in node]
    return node


def mcp_tools_to_declarations(mcp_tools):
    """MCP 도구 목록 -> Gemini 함수 선언 목록(순수 dict)."""
    decls = []
    for t in mcp_tools:
        schema = t.inputSchema or {"type": "object", "properties": {}}
        decls.append({
            "name": t.name,
            "description": (t.description or "")[:1024],
            "parameters": _clean_schema(schema),
        })
    return decls


def _result_to_text(call_result):
    """MCP tool 결과(content 블록들)를 텍스트로 합친다."""
    parts = []
    for block in (call_result.content or []):
        txt = getattr(block, "text", None)
        if txt:
            parts.append(txt)
    return "\n".join(parts) if parts else "(빈 결과)"


async def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION

    if not os.getenv("GEMINI_API_KEY"):
        print("[오류] GEMINI_API_KEY 환경변수가 없습니다.")
        print('  PowerShell:  $env:GEMINI_API_KEY="발급받은_키"')
        return

    print(f"[MCP]   {MCP_URL}")
    print(f"[모델]  {GEMINI_MODEL}")
    print(f"[질문]  {question}\n")

    gemini = genai.Client()

    async with streamablehttp_client(MCP_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tool_list = await session.list_tools()
            print("[MCP 도구]", [t.name for t in tool_list.tools], "\n")

            declarations = mcp_tools_to_declarations(tool_list.tools)
            # Gemini 3.x는 temperature/top_p/top_k 변경 비권장 → 설정하지 않음.
            config = types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=declarations)],
            )

            # 대화 히스토리 (수동 함수콜 루프)
            contents = [
                types.Content(role="user", parts=[types.Part(text=question)])
            ]

            for turn in range(MAX_TURNS):
                # 마지막 턴에서는 도구를 빼고, 지금까지 모은 정보로 답하게 강제.
                is_last = turn == MAX_TURNS - 1
                if is_last:
                    turn_config = types.GenerateContentConfig()
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part(text=(
                            "더 이상 도구를 호출하지 말고, 지금까지 검색한 장소 정보만으로 "
                            "사용자 질문에 대한 최종 답변을 한국어로 작성해줘."
                        ))],
                    ))
                else:
                    turn_config = config

                response = await gemini.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=turn_config,
                )

                cand = response.candidates[0]
                parts = cand.content.parts or []
                fcalls = [p.function_call for p in parts if getattr(p, "function_call", None)]

                # 함수콜이 없으면 -> 최종 답변
                if not fcalls:
                    print("[Gemini 답변]\n")
                    print(response.text)
                    return

                # 모델 턴(함수콜 포함)을 히스토리에 추가
                contents.append(cand.content)

                # 각 함수콜을 우리가 MCP로 실제 실행하고 결과를 모은다
                tool_response_parts = []
                for fc in fcalls:
                    args = dict(fc.args) if fc.args else {}
                    print(f"[툴콜] {fc.name}({json.dumps(args, ensure_ascii=False)})")
                    try:
                        result = await session.call_tool(fc.name, args)
                        result_text = _result_to_text(result)
                    except Exception as e:
                        result_text = f"(도구 실행 오류: {e})"
                    preview = result_text[:200].replace("\n", " ")
                    print(f"  -> 결과: {preview}{'...' if len(result_text) > 200 else ''}\n")

                    tool_response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result_text},
                        )
                    )

                # 도구 결과 턴을 히스토리에 추가하고 다시 모델에 요청
                contents.append(types.Content(role="user", parts=tool_response_parts))

            print("[경고] 최대 턴 수 도달 — 최종 답변을 얻지 못함.")


if __name__ == "__main__":
    asyncio.run(main())
