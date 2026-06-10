# RUNBOOK — 로컬 실행 & 문제해결

> 본인 PC(Windows/PowerShell)에서 게이트웨이 실행·테스트. 메인은 `../PROGRESS.md`.

---

## 로컬 실행

`app` 폴더가 보이는 위치에서:

```powershell
cd "F:\Google AI Agents Challenge\allthestreet-agent-gateway"
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8080
```

성공 신호:
```
StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8080
```
※ 이 상태가 "정상 대기 중"임 — 멈춘 게 아님. 끄려면 Ctrl+C.

## 브라우저 확인

- http://localhost:8080/              메타(3개 레이어)
- http://localhost:8080/docs          OpenAPI 문서
- http://localhost:8080/geo/spots.jsonld?page=1&page_size=3
- http://localhost:8080/ucp/feed?page=1&page_size=3
- http://localhost:8080/.well-known/ucp.json

## MCP 도구 테스트

서버 켜둔 채, 새 터미널에서:
```powershell
cd "F:\Google AI Agents Challenge\allthestreet-agent-gateway"
py mcp_test.py
```
도구 3종 목록 + search_spots / get_spot_detail / list_recent_spots 호출 결과 출력.

## 이미지 프록시 테스트 (선택)

키가 있어야 실제 이미지가 뜸:
```powershell
$env:GOOGLE_MAPS_API_KEY="<Places 키>"
py -m uvicorn app.main:app --reload --port 8080
```
키 없으면 `/img/{ref}` 는 503 — 정상(나머지 기능엔 영향 없음).

---

## 자주 만난 문제

### 1. `python` 이 'Python'만 출력하고 안 됨
Windows 앱 실행 별칭이 가로챔. → **`py`** 사용 (`py -m pip`, `py -m uvicorn`).
또는 설정 > "앱 실행 별칭"에서 python.exe/python3.exe 끄기.

### 2. `pip` Fatal error in launcher
경로 깨짐. → **`py -m pip`** 사용.

### 3. `ModuleNotFoundError: No module named 'app'`
`app` 폴더가 안 보이는 위치에서 실행 중. → `dir` 로 `app` 보이는 폴더로 `cd`.
(zip 풀 때 폴더 중첩 주의: `Expand-Archive -DestinationPath` 사용 권장)

### 4. 새 라우트가 404 (예: /ucp/feed)
코드 추가 후 서버 재시작 안 함. → Ctrl+C 후 다시 실행 (`--reload` 권장).

### 5. MCP 클라이언트 `ReadError` / `307`
`/mcp`(슬래시 없음) 요청이 `/mcp/`로 307 리다이렉트되며 끊김.
→ 해결됨: `main.py`의 `MCPSlashMiddleware`가 처리 (v0.2.1+).
   클라이언트는 `/mcp` `/mcp/` 둘 다 OK.

### 6. zip 압축이 폴더만 풀리고 파일 없음
휴지통 복원 등으로 손상. → 폴더 삭제 후 `Expand-Archive`로 새로:
```powershell
cd "F:\Google AI Agents Challenge"
Remove-Item -Recurse -Force allthestreet-agent-gateway
Expand-Archive -Path "allthestreet-agent-gateway-final.zip" -DestinationPath "." -Force
```

## 빠른 점검 명령

```powershell
# 파일 제대로 있는지
Get-ChildItem "allthestreet-agent-gateway" -File | Select-Object Name
# app 로드되는지 (uvicorn 없이)
py -c "from app.main import app; print('ok', app.version)"
```
