# PROGRESS — AllTheStreet Agent Gateway

> Google for Startups AI Agents Challenge — **Track 3**
> 최종 업데이트: 2026-06-05 · 마감: 2026-06-11 17:00 PT (= 06-12 09:00 KST)
> 상세 참고 문서는 `docs/` 하위 파일 참조.

---

## 한 줄 요약

기존 AllTheStreet 백엔드(`mukbang-backend`, Flask) 데이터를 Gemini/검색에 노출하는
**독립 read-only 게이트웨이**(FastAPI). UCP·GEO·MCP 3개 레이어를 구현해 로컬 검증 완료.
**Cloud Run 배포 완료** — 세 레이어 모두 클라우드에서 동작. 다음은 보안 마무리.

## 🚀 배포 정보 (운영 중)

- **GCP 프로젝트**: `allthestreet-gateway-2026` (크레딧 빌링 `01BACA-DB0319-2064AB` 연결)
- **리전**: `asia-northeast3` (서울)
- **Service URL (진짜)**: `https://allthestreet-agent-gateway-rfic5mxz6a-du.a.run.app`
  - ⚠️ 이전에 쓰던 `...-36051188184.asia-northeast3.run.app`는 **틀린 URL**.
    `gcloud run services describe ... --format="value(status.url)"`로 확인한
    위 `rfic5mxz6a` 가 정답. (404 헤맨 원인이 이 URL 혼동이었음)
- **현재 버전**: v0.4.0 — 콘텐츠 페이지·영상·다국어·상품 연동 + 캐싱/레이아웃/지도 개선
  - **상태: 코드 로컬 검증 완료, Cloud Run 재배포 대기** (내일 진행)
- **인프라 설정 (적용됨)**: `--memory 1Gi --min-instances 1 --timeout 300 --concurrency 80 --no-cpu-throttling`
  (min-instances 1로 콜드스타트 제거 + no-cpu-throttling으로 백그라운드 인덱스 빌드 안정화)
- **공개 엔드포인트**:
  - GEO: `/geo/spot/{id}.jsonld`, `/geo/spots.jsonld`, `/sitemap.xml`, `/robots.txt`
  - UCP: `/.well-known/ucp.json`, `/ucp/feed`, `/ucp/spot/{id}` (상품 offers 연동됨)
  - MCP: `/mcp` — 도구 3종(search_spots/get_spot_detail/list_recent_spots)
  - 페이지(A): `/p/{spot_id}` — 영상(맨 위, 언어별 1개)·Google지도·영업시간·예약/티켓·FAQ + JSON-LD
- **현재 env-vars**: SOURCE_API_BASE, CORS_ORIGINS, PUBLIC_BASE_URL, MCP_ALLOWED_HOSTS=*,
  GOOGLE_MAPS_API_KEY (지도용 — 미설정 시 OSM 폴백)
- 재배포 명령 / 절차 → `docs/DEPLOY.md`

관련 상세:
- 시스템 정찰 결과 → `docs/RECON.md`
- 아키텍처/데이터 흐름 → `ARCHITECTURE.md`
- 배포 절차 → `docs/DEPLOY.md`
- 로컬 실행/문제해결 → `docs/RUNBOOK.md`
- biz 사업자 서비스(C) 설계·발견 → `docs/BIZ_SERVICE.md`
- 확장 로드맵(데모→SaaS: 캐시추상화→Redis→SaaS분리→Pub/Sub→BigQuery) → `docs/SCALABILITY.md`

---

## 🗺️ 프론트엔드 로드맵 (확정 2026-06-05)

백엔드(게이트웨이)는 배포 완료. 이제 프론트를 A → B → C 순서로 진행.

| 순위 | 항목 | 시점 | 내용 |
|---|---|---|---|
| **1** | **A. 콘텐츠 페이지** | 최소버전+영상 완료 | **방법 1 구현됨**: `GET /p/{id}` 서버사이드 HTML (사진·지도·영업시간·FAQ·**영상**+timeframe + JSON-LD/VideoObject 임베드). 영상은 VM 수정 없이 기존 API 활용. 살붙이기(상품·목록·디자인) 남음 |
| **2** | **B. 챌린지 데모** | A 다음 | 질문 → MCP/UCP 검색 → 장소 카드 추천 → 구매링크 → A로 이동. 6/12 제출용 시연 화면. A 컴포넌트 재활용 |
| **3** | **C. biz 사업자 서비스** | **챌린지 이후 구축** | `biz.metaxtreet.com`. 외부 사업자가 자기 장소·상품 등록/관리. **설계 메모만 지금**(`docs/BIZ_SERVICE.md`), 구축은 마감 이후 |

근거: A는 백엔드의 가치를 사용자 화면으로 완성하는 토대이자 착지점. B는 A 위에 얹는
데모. C는 운영 DB를 건드리는 write 작업(사업자 회원모델·소유권·상품통합)이라 별도
중장기 과제 — 마감에 쫓겨 할 일이 아님.

---

## ✅ 오늘 완료한 일 (2026-06-05)

### Cloud Run 배포 ⭐
- 신규 프로젝트 생성 + 크레딧 빌링 연결 + API 활성화(run/build/artifactregistry).
- `gcloud run deploy --source .` 로 컨테이너 빌드·배포 성공 (서울 리전).
- PUBLIC_BASE_URL을 실제 배포 URL로 재설정 → UCP/JSON-LD canonical URL 정상.
- MCP 421(DNS-rebinding 보호) 이슈 → `MCP_ALLOWED_HOSTS` 설정으로 해결, 재배포.
- **클라우드에서 GEO/UCP/MCP 모두 동작 확인** (브라우저 + mcp_test.py).

### 프론트엔드 방향 확정 + 사업자 서비스(C) 정찰
- 프론트 로드맵 A → B → C 순서 확정 (위 로드맵 표 참조).
- **A는 방법 1(게이트웨이에 서버사이드 HTML 페이지 얹기)로 결정.**
  최소 동작 버전(장소 상세 1종: 사진·지도·영업시간·FAQ·구매링크 + JSON-LD 임베드)
  부터, 1세션 목표.
- C(사업자 서비스) 타당성 정찰: `mukbang-admin`이 진짜 관리자(vue-element-admin
  기반, 로그인·대시보드·장소/유튜브 관리 화면 보유) 확인. 단 **데이터 소유 모델
  부재 + 상품 백엔드 위치 미확정** 발견 → `docs/BIZ_SERVICE.md`에 정리.

### 정찰 (시스템 파악)
- GCP 프로젝트 식별: 소스코드는 모두 **`street-view-0315`** 의 Cloud Source Repos에 존재.
- 저장소 역할 규명: `mukbang-backend`(Flask API), `mukbang-app`(Vue 어드민),
  `vue-front-new-allthestreet`(웹 프론트) 등. → 상세 `docs/RECON.md`
- 데이터 소스 확정: `api.allthestreet.com/api_mukbang/get_spot_data_admin`
  (Authorization 헤더 없으면 통과 = 인증 없이 read 가능). 좌표·영업시간·
  Google/Naver Place ID·다국어가 모두 포함됨을 실제 응답으로 확인.
- DB: MySQL `mukbang` @ 34.64.228.95 — 외부 직접접속 차단 확인 → API 경유로 결정.
- 전체 장소 수: 약 10,183건.

### 신규 서비스 구현 (`allthestreet-agent-gateway`, FastAPI)
- **FastAPI 뼈대** — config(환경변수 기반), health 엔드포인트, Dockerfile. 로컬 구동 검증.
- **GEO 레이어** — Schema.org JSON-LD 생성 (LocalBusiness + GeoCoordinates +
  openingHoursSpecification + VideoObject + FAQPage), `/robots.txt`, `/sitemap.xml`.
  실제 데이터로 변환 검증 완료.
- **UCP 레이어** — UCP 발견 객체(다국어 name/address, geo, offers 자리, 외부ID),
  `/.well-known/ucp.json`, `/ucp/feed`, `/ucp/spot/{id}`. 검증 완료.
- **이미지 프록시** — `/img/{ref}`: photo_reference 토큰은 서버가 키를 들고
  Google Place Photo를 받아 스트리밍(키 비노출), 정상 URL은 그대로 통과.
- **MCP 레이어** — FastMCP 기반, `/mcp`에 마운트. 도구 3종:
  `search_spots`, `get_spot_detail`, `list_recent_spots`. 307 리다이렉트 이슈를
  미들웨어로 해결. **로컬에서 MCP 클라이언트로 도구 목록·호출 전부 검증 완료.**

### 검증 상태
- 세 레이어 모두 **본인 PC에서 end-to-end 동작 확인** (GEO/UCP는 브라우저,
  MCP는 `mcp_test.py` 클라이언트).

---

## ⬜ 해야 할 일 (다음 세션부터)

### ✅ 0-A. 재배포 + 검증 완료 (2026-06-09)
오늘 코드(영상 누락 버그·영상 맨 위·Google 지도) Cloud Run 반영 완료. 진짜 URL
(`...rfic5mxz6a-du.a.run.app`)로 검증: `/p/4632`(해운대블루라인파크) — 영상 맨 위
(언어별 1개)·Google 지도·상품(예약·티켓, 스카이캡슐/해변열차+kkday) 모두 정상.
`/p/1`(부촌육회, 상품·영상 없음)도 깨짐 없이 깔끔하게 표출. env-vars에
PUBLIC_BASE_URL(진짜 URL)·GOOGLE_MAPS_API_KEY(Maps Embed, API제한+리퍼러제한) 반영.

### (참고) 다음 재배포 시 명령
   ```
   gcloud run deploy allthestreet-agent-gateway --source . \
     --project allthestreet-gateway-2026 --region asia-northeast3 \
     --allow-unauthenticated --set-env-vars \
     "SOURCE_API_BASE=https://api.allthestreet.com,CORS_ORIGINS=https://korea.allthestreet.com,PUBLIC_BASE_URL=https://allthestreet-agent-gateway-rfic5mxz6a-du.a.run.app,MCP_ALLOWED_HOSTS=*,GOOGLE_MAPS_API_KEY=<키>"
   ```
   (PowerShell에서 gcloud 막히면: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` 또는 `gcloud.cmd`)

### 0. 보안
- ✅ **(완료) 게이트웨이 Maps 키 → Secret Manager**: `GOOGLE_MAPS_API_KEY`를
  평문 env-var에서 Secret Manager(`google-maps-api-key:latest`)로 이전. Cloud Run
  서비스계정(`36051188184-compute@`)에 secretAccessor 부여 →
  `--update-secrets`로 주입, 평문 env-var 제거. /p/4632 지도 정상 = 시크릿 읽기 확인.
  ⚠️ 키는 Maps Embed API 제한 + HTTP 리퍼러 제한 적용됨.
  ⚠️ 재배포 시 `--set-env-vars`에 GOOGLE_MAPS_API_KEY 다시 넣지 말 것(시크릿 덮어씀).
- ✅ **(완료) 기존 백엔드 노출 키 2건 API 제한 추가** (콘솔, 2026-06-09):
  - `...A1Ag`(allthestreet-Real-Key, scrap/google.py가 사용): 리퍼러 제한 기존 +
    API 제한 추가(Maps JavaScript/Geocoding/Places/Directions) → 공개 노출 경고 해소.
  - `...7UGE`(kroad-Admin-Key): IP 제한 기존 + API 제한 추가(지도 4종+YouTube,
    Gemini 계열 제외) → 경고 해소. admin 핵심 기능(장소·상품·유튜브·지도) 정상 확인.
- 🔴 **(남음, 백엔드 범위 — VM 접근 필요)** 평문 Gemini 키 재발급:
  `scrap/gemini.py`에 `AIzaSy***REDACTED***` 평문. street-view-0315 VM 코드라 SSH 없이
  수정 불가 → 콘솔 재발급 + 백엔드 담당자 협의. 게이트웨이는 이 키 안 씀.
- ⚠️ **(별도 이슈, 우리 무관)** admin '분기점 자동 추출' 미작동: 콘솔 에러가
  **Mixed Content**(HTTPS 페이지가 HTTP predict/nodeEdge 추출서버 호출 → 브라우저
  차단). **API 키 제한과 무관**(보안작업 영향 아님). 추출서버 HTTP→HTTPS 전환 필요 =
  기존 백엔드 인프라 영역, 별도 처리.

### 1. A — 콘텐츠 페이지 (최소버전 + 영상연동 완료)
- ✅ **방법 1 구현·검증 완료**: `GET /p/{spot_id}` 서버사이드 HTML
  (히어로 이미지·요일별 영업시간·OSM 지도·FAQ·영상 + JSON-LD 임베드).
- ✅ **영상 연동 완료 — VM 수정 없이 해결**:
  - 기존 `get_video_data` 응답의 각 영상에 `spots[]`(spot_id·spot_timeframe·
    spot_videos)가 이미 포함됨을 발견. 별도 엔드포인트/VM 접근 불필요.
  - `app/data/videos.py`: 피드를 받아 `{spot_id: [VideoRef]}` 인덱스를 메모리
    캐싱(TTL 12h, asyncio Lock으로 동시 빌드 직렬화). `repository.get_spot()`이 첨부.
  - 페이지: 썸네일·제목·timeframe·**언어 배지** 카드. **언어별(한/일/영) 최신
    1개씩만** 노출(제목 문자로 언어 판별, publish_time 최신순). JSON-LD:
    VideoObject + `Clip` startOffset(영상 내 장소 등장 시각).
- ✅ **(오늘) 영상 누락 버그 수정**: VideoIndex의 `_building` 조기 리턴이 콜드스타트
  동시 요청 시 빈 결과를 반환해 영상이 사라지던 문제 → asyncio Lock + TTL 12h +
  타임아웃 60s + 시작 시 백그라운드 빌드로 해결. (spot 인덱스와 동일 패턴) 검증 완료.
- ✅ **(오늘) 레이아웃: 영상을 페이지 맨 위로** 이동(주소·영업시간·상품·지도보다 위).
- ✅ **(오늘) 지도 OSM → Google Maps Embed**: `GOOGLE_MAPS_API_KEY` 있으면 Google
  (place_id 있으면 place 모드, 없으면 view 모드), 없으면 OSM 폴백. 키 필요.
- ✅ **장소 단건 조회 해결 — 3단 캐싱**: 백엔드가 spot_id 필터 미지원이라
  `{spot_id: Spot}` 인메모리 인덱스 사용. (1) 서버 시작 시 백그라운드 전체 구축
  (~1만개), (2) 캐시 히트 즉시 반환, (3) 미스 시 최신 페이지 lazy 보충(신규 spot).
  전체 재구축 TTL 12h. 이제 모든 spot_id를 `/p/{id}`로 즉시 열 수 있음.
  (예: 해운대블루라인파크 = spot_id 4632 = product_id 22)
- ✅ **상품(commerce) 연동 완료 — UCP의 핵심 목적 달성**:
  - 데이터 발견: `/api_mukbang/products`(목록 622개, linked_spots) +
    `/api_mukbang/product/{id}`(상세, `product_extra`(str JSON)에 commerce[] —
    언어별 name·out_link(kkday 딥링크)·options[price.normal/discount, stock]). 인증 불요.
  - 연동: spot 행에 `product_id`가 직접 있어, 그 id로 `product/{id}` **1회만**
    호출(622개 순회 불필요). `_parse_commerce`가 언어별 파싱. 상품 없는 spot은
    호출 안 함. `repository.get_spot()`이 첨부.
  - UCP `offers`(가격·통화·deeplink·재고), 페이지 "예약·티켓" 섹션(가격·예약버튼),
    GEO `makesOffer`(Offer price/url/availability). mock 검증 완료.
  - **결제는 kkday 외부 딥링크로 위임 → Stripe/한국 결제 이슈와 무관하게 동작.**
- ✅ **다국어 `@language` 태깅 완료**: JSON-LD의 name·alternateName·address를
  한/영/일 언어 태깅 배열로 출력 → Gemini가 각 텍스트 언어를 인식, 사용자 언어로
  번역·인용 가능. (UCP는 LocalizedText로 이미 다국어 구분됨)
- 이후 살 붙이기: 상품 상세, 목록/탐색, 디자인 다듬기, 페이지 hreflang/영어 버전.
- 데이터 보강(공통): FAQ 자동 생성(기존 Gemini 추출기 연계), 다국어 상품 desc 활용.

### 2. B — 챌린지 데모 (A 다음, 6/12 제출)
- 질문 → MCP/UCP 검색 → 장소 카드 → 구매링크 → A로 이동, 시연 화면.
- **결정: B-1(실제 Gemini 툴콜, 풀 에이전트)로 진행.**
- ✅ **B-1 1단계 완료 (로컬 검증, 2026-06-09)**: `demo/gemini_mcp_demo.py`.
  실제 Gemini가 우리 원격 MCP(`/mcp`)를 호출 → 우리 데이터로 답변하는 것 확인.
  - 질문("부산 해운대 가볼 곳+티켓") → Gemini가 `search_spots`를 7회 자동 호출
    (해운대/블루라인파크/아쿠아리움/요트 등) → 우리 spot 데이터 검색 → 블루라인파크
    (4632)·씨라이프·더베이101·노티드 등 추천 + **각 장소 `/ucp/spot/{id}` 링크 포함**
    최종 답변 생성. = 에이전틱 발견(Discovery) 흐름 실증.
  - **구현 핵심(중요 교훈)**: google-genai는 config를 deepcopy → MCP '세션 객체'를
    config.tools에 직접 넣으면 `cannot pickle '_asyncio.Future'`로 실패(FastMCP/표준
    SDK 공통). 해결: 세션을 넣지 않고 **MCP 도구 스키마 → Gemini function_declarations
    (순수 JSON)** 로만 전달, 함수콜은 **우리가 직접 MCP로 실행**(수동 오케스트레이션)
    후 결과를 되돌림. SDK 버전 비의존 + 결과 가공 자유(B-2/B-3에 유리).
  - 모델: **`gemini-3.5-flash`** (gemini-2.0-flash는 2026-06-01 종료됨). Gemini 3.x는
    temperature/top_p/top_k 비권장 → 설정 안 함. SDK는 google-genai v2.0.0+ 권장.
  - 새 Gemini API 키: AI Studio에서 발급, allthestreet-gateway-2026 프로젝트,
    서버 전용(노출 백엔드 키들과 무관, 깨끗한 신규 키).
- ✅ **B-1 2·3단계 완료 (배포·검증, 2026-06-09)**: 게이트웨이에 `/demo` 추가.
  - `GET /demo` Gemini-웹-챗 스타일 페이지(인삿말·예시칩·하단 알약 입력창·블루퍼플
    그라데이션·라이트/다크) + `POST /demo/ask`. 가짜 단계 로딩 → 결과.
  - 흐름: 질문 → 툴칩(Gemini가 우리 MCP 호출 증명, 펼치면 툴콜 로그) → 답변(마크다운)
    → 장소 카드(영상 썸네일▶ + 가격·할인 + 예약·상세 버튼).
  - 로직: `app/demo/agent.py` — B-1 1단계 함수콜 흐름을 게이트웨이 내부로(외부 MCP
    HTTP 없이 SpotRepository 직접). 검색 spot에 상품+영상 자동 첨부.
  - **다국어 (방식 C: 자동+토글 자동/한국어/EN/日本語)**: 답변·상품설명은 선택/감지
    언어로 완전 대응(system_instruction); 장소명·주소는 ko/en 데이터 있는 만큼(ja는
    en 폴백); 영상은 해당 언어 우선; 버튼·UI 텍스트는 ko/en/ja 사전으로 현지화.
  - **카드 필터**: 답변 본문의 `/ucp/spot|/p/{id}` 링크를 등장 순서로 추출 → 추천한
    장소만 그 순서로 카드(`_spots_in_answer_order`).
  - Gemini 키는 Secret Manager(`gemini-api-key:latest`) 주입. 모델 gemini-3.5-flash.
    requirements에 google-genai 추가. 배포·검증 완료(ko/en/ja 동작 확인).

### 3. 제출 준비 (Devpost)
- 데모 시나리오 + README/OpenAPI 정리 + 프로젝트 페이지 + **Submit 클릭**.

### 4. C — biz 사업자 서비스 (챌린지 이후 본격 구축)
- 설계·발견 사항은 `docs/BIZ_SERVICE.md` 에 정리됨. 마감 이후 착수.

---

## ❓ 정해지지 않은 일 (결정 필요)

- **기존 백엔드 VM 접근 권한**: `api.allthestreet.com`은 GCP VM에서 Flask 직접 구동.
  영상 연동은 우회 해결(VM 불필요)했으나, 향후 백엔드 수정(단일 spot read, 상품 등)
  이나 C 서비스에는 SSH 접근·재시작 권한이 필요 — **현재 없음**. 권한 경로 확인 필요.
- **MCP 인증**: 현재 `/mcp` 공개 + `MCP_ALLOWED_HOSTS=*`. Gemini Enterprise 연동 시
  API 키/OAuth 적용 여부, 호스트 화이트리스트로 좁힐지.
- **상품 연계 데이터**: 상품(kkday) 백엔드가 어느 DB/저장소에 있는지 미확정.
  `mukbang` DB엔 상품 테이블 없음(PayInfo=주문기록, PrepaidCard=선불카드).
  A의 구매링크와 C 모두에 영향 → 상세 `docs/BIZ_SERVICE.md`.
- **B 데모 형태**: B-1(실제 Gemini 툴콜) 확정·1단계 검증 완료. 남은 결정 — 2단계
  웹 UI를 별도 앱으로 둘지 게이트웨이에 `/demo` 엔드포인트로 얹을지.
- **Marketplace 상장 범위**: 이번 제출은 "배포 + 데모"까지인지, 실제 리스팅까지인지.
- **커스텀 도메인**: `gateway.allthestreet.com` 사용 여부 (현재는 run.app URL 사용 중).

## ✅ 확정된 사항

- GCP 프로젝트: 신규 `allthestreet-gateway-2026` (기존과 분리), 크레딧 빌링 연결.
- 리전: `asia-northeast3` (서울).
- 데이터 접근: 기존 Flask API(`get_spot_data_admin`) HTTP read-only 경유.

---

## 현재 프로젝트 구조

```
allthestreet-agent-gateway/
├── app/
│   ├── main.py            # FastAPI + MCP 마운트 + 슬래시 미들웨어
│   ├── config.py          # 환경변수 설정
│   ├── data/
│   │   ├── repository.py  # 기존 API read-only 조회 + 정규화
│   │   └── images.py      # 이미지 URL/photo_reference 처리
│   ├── geo/jsonld.py      # Schema.org JSON-LD 생성
│   ├── ucp/               # schema.py, adapter.py
│   ├── mcp/server.py      # MCP 서버 (도구 3종)
│   └── routes/            # geo_routes, ucp_routes, image_routes, health
├── Dockerfile
├── requirements.txt
├── README.md
├── ARCHITECTURE.md
└── docs/                  # RECON / DEPLOY / RUNBOOK (참고 문서)
```
