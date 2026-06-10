# AllTheStreet Travel Agent Gateway

Google for Startups AI Agents Challenge — **Track 1 (Build: MCP-connected net-new agent)**
기존 AllTheStreet 데이터를 Gemini/검색엔진에 노출하는 read-only 게이트웨이.
레이어: **GEO (JSON-LD)** · **UCP** · **MCP** · **콘텐츠 페이지(A)** → 모두 구현됨

> 📌 진행상황·다음할일: `PROGRESS.md` · 정찰결과: `docs/RECON.md` ·
> 배포절차: `docs/DEPLOY.md` · 로컬실행/문제해결: `docs/RUNBOOK.md`

## 구조

```
allthestreet-agent-gateway/
├── Dockerfile            # Cloud Run 컨테이너
├── requirements.txt
├── .env.example          # 환경변수 예시 (비밀값 없음)
└── app/
    ├── main.py           # FastAPI 진입점
    ├── config.py         # 환경변수 설정
    ├── data/repository.py # 기존 API read-only 조회 + 정규화
    ├── geo/jsonld.py     # Spot → Schema.org JSON-LD
    ├── ucp/              # schema.py, adapter.py (UCP 발견 객체)
    ├── mcp/server.py     # MCP 서버 (search_spots / get_spot_detail / list_recent_spots)
    └── routes/           # geo_routes.py, ucp_routes.py, image_routes.py, health.py
```

## MCP (Gemini 등 에이전트 연결)

MCP 서버가 같은 FastAPI 서비스의 `/mcp` 에 streamable-HTTP로 마운트되어 있다.
MCP 클라이언트(Gemini Enterprise / Claude 등)는 `{PUBLIC_BASE_URL}/mcp` 로 연결한다.

도구:
- `search_spots(keyword, limit, lang)` — 키워드로 장소 검색
- `get_spot_detail(spot_id, lang)` — 장소 상세(UCP 객체: 좌표·영업시간·영상·외부ID)
- `list_recent_spots(limit, lang)` — 최근 큐레이션 장소 샘플

## 로컬 실행

```bash
cd allthestreet-agent-gateway
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

확인:
- http://localhost:8080/            서비스 메타
- http://localhost:8080/docs        OpenAPI 문서 (Marketplace 상장용 명세)
- http://localhost:8080/healthz     헬스체크
- http://localhost:8080/robots.txt  크롤러 허용 (Googlebot/GPTBot 등)
- http://localhost:8080/geo/spots.jsonld?page=1&page_size=3   장소 목록 JSON-LD
- http://localhost:8080/geo/spot/474.jsonld                   단일 장소 JSON-LD
- http://localhost:8080/.well-known/ucp.json                  UCP 매니페스트
- http://localhost:8080/ucp/feed?page=1&page_size=3           UCP 발견 피드
- http://localhost:8080/ucp/spot/474                          단일 UCP 객체
- http://localhost:8080/p/474                                 콘텐츠 페이지(HTML, A)

## 데이터 소스

기존 Flask 백엔드 `api.allthestreet.com/api_mukbang/get_spot_data_admin` 를
HTTP로 읽는다 (Authorization 헤더 없이 — 레거시 패스스루). DB 직접 접속 없음.
`spot_detail` 안의 Google Places JSON(좌표·영업시간·전화)을 파싱해 활용.

## Cloud Run 배포 (예시)

```bash
gcloud run deploy allthestreet-agent-gateway \
  --source . \
  --project street-view-0315 \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars "PUBLIC_BASE_URL=https://<배포후-URL>,SOURCE_API_BASE=https://api.allthestreet.com"
```

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SOURCE_API_BASE` | https://api.allthestreet.com | 업스트림 데이터 소스 |
| `PUBLIC_BASE_URL` | https://gateway.allthestreet.com | JSON-LD canonical URL 생성용 (배포 후 실제 URL로) |
| `CORS_ORIGINS` | https://korea.allthestreet.com | CORS 허용 origin (쉼표 구분) |
| `GATEWAY_API_KEY` | (없음) | MCP 등 보호 surface용 (선택) |
| `ENV` | development | 환경 표시 |

## TODO (다음 단계)

- [x] UCP 어댑터 (`app/ucp/`) + `/.well-known/ucp.json`
- [x] 이미지 프록시 (`/img/{ref}`) — Google Place photo, 키 서버측 보관
- [x] MCP 서버 (`app/mcp/`) — search_spots / get_spot_detail / list_recent_spots, /mcp 마운트
- [ ] 단일 spot read 엔드포인트를 기존 백엔드에 추가 (현재는 페이지 스캔)
- [ ] 상품(kkday) 연계 → UCP offers / GEO Offer 채우기
- [ ] Cloud Run 배포 + Secret Manager 연동 (GOOGLE_MAPS_API_KEY 포함)
- [ ] 노출된 Gemini / Places API 키 폐기 (기존 백엔드 보안 이슈)

## 이미지 프록시 참고

`images` 필드는 (1) 정상 URL과 (2) Google Places photo_reference 토큰이 섞여 있다.
정상 URL은 그대로, 토큰은 `/img/{ref}` 프록시 URL로 변환된다. 프록시가 동작하려면
`GOOGLE_MAPS_API_KEY` 환경변수가 필요하다 (없으면 503). 기존 백엔드가 쓰던 Places
키를 재사용 가능. 키는 절대 클라이언트 응답에 노출되지 않는다.
