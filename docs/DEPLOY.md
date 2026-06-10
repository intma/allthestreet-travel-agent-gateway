# DEPLOY — Cloud Run 배포 절차

> 메인 진행상황은 `../PROGRESS.md`. 아래 "빠른 재배포"가 실전 명령.

---

## ⚡ 빠른 재배포 (코드 수정 후 매번 쓰는 명령)

배포 완료됨(v0.4.0). 코드 바꾼 뒤 로컬 PowerShell, 코드 폴더에서 한 줄:

```powershell
gcloud run deploy allthestreet-agent-gateway --source . --project YOUR_PROJECT_ID --region asia-northeast3 --allow-unauthenticated --set-env-vars "SOURCE_API_BASE=https://api.allthestreet.com,CORS_ORIGINS=https://korea.allthestreet.com,PUBLIC_BASE_URL=https://YOUR-SERVICE.run.app,MCP_ALLOWED_HOSTS=*"
```

- **진짜 Service URL은 `describe로 얻은 실제 URL`** (describe로 확인). `YOUR_PROJECT_NUMBER` 형식은 틀림.
- `--set-env-vars`는 덮어쓰기. **GOOGLE_MAPS_API_KEY는 넣지 말 것** — Secret Manager로
  관리 중이며, env-var에 다시 넣으면 시크릿 연결이 덮어써짐. (위 4개만 지정)
- 인프라 설정(min-instances 1, no-cpu-throttling 등)·시크릿 연결은 deploy가 유지함.
- `gcloud` 실행정책 막힐 때: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` 또는 `gcloud.cmd`.
- 검증: 브라우저로 `{Service URL}/p/4632` (영상·지도·상품), 첫 로드는 인덱스 구축으로 느림.

---

## (참고) 최초 배포 절차

## 사전 준비

- `gcloud` 로그인 + 프로젝트 설정
  ```bash
  gcloud auth login
  gcloud config set project street-view-0315
  ```
- 필요한 API 활성화 (Cloud Run, Cloud Build, Artifact Registry)
  ```bash
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com --project street-view-0315
  ```

## 1단계 — 일단 배포 (키 없이, 동작 확인)

이미지 프록시(`/img`)는 키가 없으면 503이지만 나머지(GEO/UCP/MCP)는 정상 동작.
먼저 파이프라인부터 검증.

```bash
cd "F:\Google AI Agents Challenge\allthestreet-agent-gateway"

gcloud run deploy allthestreet-agent-gateway \
  --source . \
  --project street-view-0315 \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars "SOURCE_API_BASE=https://api.allthestreet.com,CORS_ORIGINS=https://korea.allthestreet.com"
```

배포 완료 시 출력되는 URL(예: `https://allthestreet-agent-gateway-xxxx.a.run.app`)을 기록.

## 2단계 — PUBLIC_BASE_URL 재설정

JSON-LD의 canonical @id/url, UCP url, 이미지 프록시 URL이 이 값을 기준으로 생성됨.
1단계에서 받은 실제 URL로 다시 설정.

```bash
gcloud run services update allthestreet-agent-gateway \
  --project street-view-0315 --region asia-northeast3 \
  --update-env-vars "PUBLIC_BASE_URL=https://<배포된-URL>"
```

## 3단계 — 배포 검증

```
https://<URL>/                         메타 (3개 레이어 표시)
https://<URL>/docs                     OpenAPI 문서
https://<URL>/geo/spots.jsonld?page=1&page_size=3
https://<URL>/ucp/feed?page=1&page_size=3
https://<URL>/.well-known/ucp.json
https://<URL>/robots.txt
```
MCP는 클라이언트로: `mcp_test.py`의 URL을 `https://<URL>/mcp` 로 바꿔 실행.

## 4단계 — 키를 Secret Manager로 (보안 마무리)

```bash
# 1) 시크릿 생성 (값은 프롬프트로 입력하거나 파일에서)
echo -n "<GOOGLE_MAPS_KEY>" | gcloud secrets create google-maps-key \
  --data-file=- --project street-view-0315

# 2) Cloud Run 서비스 계정에 접근 권한
#    (PROJECT_NUMBER는 gcloud projects describe 로 확인)
gcloud secrets add-iam-policy-binding google-maps-key \
  --project street-view-0315 \
  --member "serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor

# 3) 시크릿을 환경변수로 마운트
gcloud run services update allthestreet-agent-gateway \
  --project street-view-0315 --region asia-northeast3 \
  --update-secrets "GOOGLE_MAPS_API_KEY=google-maps-key:latest"
```

> 주의: 이 키는 폐기·재발급한 **새 키**를 넣을 것. 기존 노출 키는 폐기.
> Places 키에 referrer 제한이 있으면 서버 호출이 막힘 → 서버용 키 사용.

## 참고 — gcloud 없이 빌드만 로컬 확인

```bash
docker build -t ats-gateway .
docker run -p 8080:8080 -e SOURCE_API_BASE=https://api.allthestreet.com ats-gateway
```

## 알려진 고려사항

- Cloud Run은 요청당 `PORT`(기본 8080) 주입 — Dockerfile이 `${PORT}` 바인딩하도록 돼 있음.
- MCP 세션은 인메모리. Cloud Run 다중 인스턴스 시 세션 고정 필요할 수 있음
  (초기 데모는 min-instances=1 또는 동시성 조정으로 단순화 가능).
- 업스트림(`api.allthestreet.com`) 응답 지연 대비 httpx timeout 15s 설정돼 있음.

---

## /demo (B-1) — Gemini 키 Secret Manager + 배포

데모(`/demo`)는 서버에서 Gemini를 호출하므로 `GEMINI_API_KEY`가 게이트웨이에
필요하다. Maps 키와 동일하게 **Secret Manager**로 주입한다 (평문 env-var 금지).

```bash
# 1) Gemini 키 시크릿 생성 (AI Studio에서 발급한 새 키, 서버 전용)
printf "AIza...실제키" | gcloud secrets create gemini-api-key \
  --project YOUR_PROJECT_ID --data-file=-

# 2) Cloud Run 서비스계정에 접근 권한 (PROJECT_NUMBER=YOUR_PROJECT_NUMBER)
gcloud secrets add-iam-policy-binding gemini-api-key \
  --project YOUR_PROJECT_ID \
  --member "serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor

# 3) 시크릿을 환경변수로 주입 (Maps 키 주입은 유지됨)
gcloud run services update allthestreet-agent-gateway \
  --project YOUR_PROJECT_ID --region asia-northeast3 \
  --update-secrets "GEMINI_API_KEY=gemini-api-key:latest"
```

그 후 코드 반영 재배포(빠른 재배포 명령). requirements.txt에 google-genai 추가됨
→ `--source .` 빌드 시 자동 설치. 검증: 브라우저로 `{Service URL}/demo` → 예시 칩
클릭 → 콘솔에 도구 호출 로그 + 답변 + 장소 카드.

주의:
- `GEMINI_API_KEY`도 `--set-env-vars`에 넣지 말 것(시크릿 덮어씀). GOOGLE_MAPS_API_KEY와 동일.
- 첫 /demo 요청은 인덱스 미빌드 시 느릴 수 있음(다른 엔드포인트와 동일). min-instances 1로 완화.
- gemini-2.0-flash는 2026-06-01 종료 → GEMINI_MODEL 기본값 gemini-3.5-flash.
