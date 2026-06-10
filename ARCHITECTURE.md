# AllTheStreet — UCP / GEO / MCP 서비스 설계서

> Google for Startups AI Agents Challenge — **Track 3 (Refactor for Google Cloud Marketplace & Gemini Enterprise)**
> 작성 기준일: 2026-06-05 · 로컬 작업 경로: `F:\Google AI Agents Challenge` · 배포: GCP Cloud Run

---

## 0. 한 줄 요약

기존 AllTheStreet 백엔드(`mukbang-backend`, Flask)가 보유한 **숏폼 영상 기반 장소·상품 데이터**를, Gemini가 발견·인용·추천할 수 있도록 **UCP(표준 JSON) · GEO(JSON-LD) · MCP(질의 도구)** 3개 레이어로 노출하는 **독립 신규 서비스**를 구축하고 Cloud Run에 배포한다. 기존 운영 백엔드는 건드리지 않고 데이터 소스로만 사용한다.

---

## 1. 현황 진단 (정찰 결과)

### 1.1 기존 시스템 구성 (GCP 프로젝트: `street-view-0315`)

| 저장소 | 역할 | 스택 |
|---|---|---|
| `mukbang-backend` | 콘텐츠 API 서버 (`api.allthestreet.com`) | **Flask (Python)**, peewee ORM, SocketIO |
| `mukbang-app` | 관리자 대시보드 | Vue (vue-element-admin) |
| `vue-front-new-allthestreet` | 신규 웹 프론트 (`korea.allthestreet.com`) | Vue |
| `new-all-the-street` | 신버전 통합 | (확인 필요) |
| `mukbang-admin` | 상품/장소 등록 SaaS | (확인 필요) |
| `allthestreet` | 구버전/루트 | (확인 필요) |

### 1.2 데이터 계층

- **DB:** MySQL `mukbang` @ `34.64.228.95:3306` (GCP 호스팅)
- **이미지:** Cloud Storage 공개 버킷 `kmukbang_images`
- **실시간:** Firestore (`allthestreet-kmukbang` 프로젝트)

### 1.3 Gemini의 현재 용도 (중요)

`scrap/gemini.py`는 **여행계획 에이전트가 아니다.** 실제 역할은 콘텐츠 수집 파이프라인의 **데이터 추출기**:
SNS 영상 설명 텍스트 → Gemini(`gemini-2.0-flash`) → 음식점명·위치·타임프레임 JSON 추출 → DB 적재.

즉 이 플랫폼은 **"숏폼 영상 → 장소 큐레이션"** 시스템이며, 사용자가 요청한 UCP/GEO/MCP는 이 큐레이션 데이터를 **Gemini에 노출**시키는 신규 과제다.

### 1.4 핵심 데이터 모델 `SpotInfo` (GEO/UCP 재료)

| 필드 | 용도 | 상태 |
|---|---|---|
| `spot_lat`, `spot_lng` | JSON-LD `Place.geo` | ✅ 보유 |
| `spot_google_place_id` | Google Place ID 매핑 (Maps 연동) | ✅ 보유 |
| `spot_naver_place_id` | Naver 연동 | ✅ 보유 |
| `spot_address` | `Place.address` | ✅ 보유 |
| `spot_name`, `spot_name_kr` | 다국어 `name` | ✅ 보유 |
| `spot_detail`, `spot_detail_naver` | `description` / FAQ 원천 | ✅ 보유 |
| `spot_thumbnail_url` | 고해상도 썸네일 | ✅ 보유 |
| `spot_relate_video` | Video-to-Place 매핑 | ✅ 보유 |
| `spot_region` | 지역 | ✅ 보유 |
| 영업시간 / 가격 / 예약링크 | `LocalBusiness.openingHours`, `Offer` | ⚠️ 부분/없음 → 상품 테이블 또는 admin 입력으로 보완 |

> 결론: **GEO/UCP 구현에 필요한 핵심 데이터(좌표·Place ID·영상매핑)는 이미 존재한다.** `groups_with_spots` API가 응답에서 좌표를 생략했을 뿐, DB에는 있다.

---

## 2. 식별된 리스크 / 선결 과제

| # | 항목 | 조치 |
|---|---|---|
| R1 | **Gemini API 키 평문 노출** (`gemini.py`에 하드코딩, git 히스토리에 영구 저장) | 🔴 키 폐기(rotate) 후 Secret Manager 이전 |
| R2 | **DB 접속정보 평문** (`models.py`에 host/user/passwd 하드코딩) | 🔴 신규 서비스는 **read-only 전용 계정** + Secret Manager |
| R3 | **CORS 전체 허용** (`CORS(app)`, `cors_allowed_origins="*"`) | 🟡 신규 서비스는 Origin 화이트리스트 |
| R4 | 영업시간·가격·예약링크 데이터 부재 | 🟡 상품(kkday) 연계 테이블 확인 또는 admin 입력 필드 추가 |

> R1, R2는 Track 3 "엔터프라이즈 보안 적합성" 평가 항목과 직결된다.

---

## 3. 타겟 아키텍처

```
                          ┌─────────────────────────────────────┐
                          │            Gemini / Vertex AI         │
                          │   (Gemini Enterprise / Extensions)    │
                          └──────────────┬───────────────┬────────┘
                                         │ MCP           │ HTTP crawl / fetch
                                         │ (tools)       │ (JSON-LD, UCP feed)
                          ┌──────────────▼───────────────▼────────┐
                          │   🆕 NEW SERVICE  (Cloud Run, Python)  │
                          │   "allthestreet-agent-gateway"        │
                          │                                       │
                          │   ┌─────────┐ ┌────────┐ ┌─────────┐  │
                          │   │  UCP    │ │  GEO   │ │  MCP    │  │
                          │   │ adapter │ │ JSON-LD│ │ server  │  │
                          │   └────┬────┘ └───┬────┘ └────┬────┘  │
                          │        └──────────┼───────────┘       │
                          │             data access layer         │
                          │        (read-only, repository)        │
                          └──────────────────┬────────────────────┘
                                             │ read-only
                       ┌─────────────────────┼──────────────────────┐
                       │                      │                      │
              ┌────────▼────────┐   ┌─────────▼────────┐   ┌─────────▼────────┐
              │ MySQL `mukbang` │   │  기존 Flask API   │   │ Cloud Storage    │
              │ (SpotInfo 등)    │   │ api.allthestreet  │   │ kmukbang_images  │
              │ 34.64.228.95     │   │ (보조/검증용)     │   │ (썸네일)         │
              └─────────────────┘   └──────────────────┘   └──────────────────┘
                       ▲
                       │ (변경 없음 — 데이터 소스로만 사용)
              ┌────────┴─────────┐
              │ 기존 수집 파이프라인 │  SNS영상 → gemini.py 추출 → DB
              └──────────────────┘
```

핵심 원칙:
- 신규 서비스는 **기존 백엔드를 수정하지 않는다.** DB는 **read-only**로 읽는다.
- 3개 레이어(UCP/GEO/MCP)는 같은 **data access layer**를 공유한다 (중복 제거).
- 비밀값은 전부 **Secret Manager**, 컨테이너는 **Cloud Run**.

---

## 4. 데이터 접근 전략 (확정: 방법 ② DB 직접 read-only + ① 보조)

- **주 경로:** MySQL `mukbang` 직접 read-only 조회 (peewee 모델 일부 재사용). 좌표·PlaceID·영상매핑 등 전 필드 접근 → GEO 품질 최상.
- **보조 경로:** 일부 가공 데이터는 기존 Flask API(`groups_with_spots` 등) 호출로 보완 가능.
- **보안:** 운영 계정이 아닌 **`ucp_readonly` 신규 MySQL 계정**(SELECT only) 생성 권장. 접속정보는 Secret Manager.

---

## 5. 신규 프로젝트 구조 (`F:\Google AI Agents Challenge`)

```
F:\Google AI Agents Challenge\
└── allthestreet-agent-gateway\          # 신규 Cloud Run 서비스 (Python)
    ├── app\
    │   ├── __init__.py
    │   ├── main.py                       # FastAPI 진입점 (UCP/GEO 라우트)
    │   ├── config.py                     # Secret Manager / env 설정
    │   ├── data\
    │   │   ├── models.py                 # SpotInfo 등 read-only peewee 모델
    │   │   └── repository.py             # 조회 함수 (spots, groups, products)
    │   ├── ucp\
    │   │   ├── schema.py                  # UCP Pydantic 스키마
    │   │   └── adapter.py                 # SpotInfo → UCP JSON 변환
    │   ├── geo\
    │   │   ├── jsonld.py                  # Schema.org JSON-LD 생성기
    │   │   └── templates\                 # Place/LocalBusiness/Offer/VideoObject
    │   ├── mcp\
    │   │   └── server.py                  # MCP 서버 (tools 정의)
    │   └── routes\
    │       ├── ucp_routes.py              # /ucp/... , /.well-known/...
    │       ├── geo_routes.py              # /geo/spot/{id}.jsonld, sitemap.xml
    │       └── health.py
    ├── tests\
    ├── Dockerfile                         # Cloud Run 컨테이너
    ├── requirements.txt
    ├── .env.example                       # 비밀값 없음 (Secret Manager 참조)
    ├── cloudbuild.yaml                    # CI/CD (선택)
    └── README.md
```

> 기술 선택: 신규 서비스는 **FastAPI** 권장 (자동 OpenAPI 문서 → Marketplace 상장·문서화에 유리, async, Pydantic으로 UCP 스키마 검증). 기존 Flask와는 독립.

---

## 6. 레이어별 설계

### 6.1 UCP 레이어 (발견 / Discovery)

목표: 장소·상품을 Gemini가 읽는 **표준 JSON 구조**로 제공.

- **엔드포인트(안):**
  - `GET /ucp/feed` — 전체 상품/장소 피드 (페이지네이션)
  - `GET /ucp/spot/{spot_id}` — 단일 장소 UCP 객체
  - `GET /ucp/product/{id}` — 단일 상품(티켓/이용권) UCP 객체
  - `GET /.well-known/ucp.json` — UCP 디스커버리 매니페스트
- **UCP 객체(안):** `id, type(Place|Product), name(다국어), geo{lat,lng}, address, category, images[], availability, offers[{price,currency,url,deepLink}], relatedVideos[{url,timeframe}], external_ids{google_place_id,naver_place_id}`
- **변환:** `SpotInfo` / 상품테이블 → UCP 스키마 매핑 (`ucp/adapter.py`).

### 6.2 GEO 레이어 (생성형 엔진 최적화)

목표: 장소·상품·서비스가 Gemini/검색에 **인용·노출**되게.

- **JSON-LD 생성 (`geo/jsonld.py`):**
  - `Place` / `LocalBusiness` — name, geo, address, openingHours, amenityFeature
  - `Product` + `Offer` — 가격/재고/예약 deeplink (상품 연계)
  - `VideoObject` + `hasPart` — 숏폼 영상 ↔ 장소 타임프레임 매핑 (`spot_relate_video` 활용)
  - `FAQPage` — 자연어 Q&A (PDF 샘플의 8개 FAQ 형식)
  - `BreadcrumbList`, `ImageObject` (고해상도 썸네일)
- **엔드포인트(안):**
  - `GET /geo/spot/{spot_id}.jsonld`
  - `GET /geo/group/{group_id}.jsonld`
  - `GET /sitemap.xml` — 전체 장소/상품 URL (Search Console 등록용)
  - `GET /robots.txt` — Googlebot, Google-InspectionTool, GPTBot, OAI-SearchBot 허용
- **IPTC/DigitalSourceType:** AI 생성 이미지엔 태그 명시 (PDF 요건).

### 6.3 MCP 레이어 (연결 / Context)

목표: Gemini가 AllTheStreet 데이터를 **실시간 질의**하는 MCP 서버.

- **도구(tools) 정의(안):**
  - `search_spots(region, category, keyword, lang)` → 장소 리스트
  - `get_spot_detail(spot_id, lang)` → 장소 상세 (좌표·영상·FAQ 포함)
  - `get_spots_by_video(video_url)` → Video-to-Place 매핑 조회
  - `list_groups(region)` → 큐레이션 그룹 (예: "부산 빵지순례")
  - `get_product_offers(spot_id)` → 예약/티켓 상품·가격·딥링크
- **전송:** MCP over HTTP(SSE) — Cloud Run에서 서빙. Gemini Extension/Enterprise에서 연결.
- **인증:** API 키 또는 OAuth (엔터프라이즈 요건). Secret Manager.

---

## 7. Track 3 상장 체크리스트 (Marketplace / Gemini Enterprise)

- [ ] 컨테이너화 (Dockerfile) + Cloud Run 무중단 배포
- [ ] 비밀값 Secret Manager 이전 (R1 Gemini 키, R2 DB 계정)
- [ ] read-only DB 계정 분리 (R2)
- [ ] OpenAPI 문서 자동화 (FastAPI) → 상장용 API 명세
- [ ] 인증·과금 경계 설계 (API 키/OAuth, 사용량 로깅)
- [ ] 관측성: Cloud Logging / Monitoring / Trace 연동
- [ ] CORS·robots 정책 정비 (R3)
- [ ] MCP 서버 표준 준수 (도구 스키마, 에러 처리)
- [ ] 헬스체크 / readiness 엔드포인트
- [ ] README + 배포 가이드 + 데모 시나리오

---

## 8. 작업 순서 (마감: 2026-06-06 09:00 KST)

> 시간이 매우 촉박하므로 **데모 가능한 핵심 경로**부터 수직으로 완성한다.

1. **스캐폴딩** — 프로젝트 구조 + FastAPI + Dockerfile + read-only 모델/repository (DB 연결 확인)
2. **GEO 최소기능** — `/geo/spot/{id}.jsonld` 1개 라우트 + Place/VideoObject/FAQ 생성 → 실제 spot으로 검증
3. **UCP 최소기능** — `/ucp/spot/{id}` + `/.well-known/ucp.json`
4. **MCP 서버** — `search_spots`, `get_spot_detail` 2개 도구부터
5. **Cloud Run 배포** — 컨테이너 빌드 → 배포 → 공개 URL 확보
6. **검증** — JSON-LD 유효성(Rich Results Test), sitemap/robots, MCP 연결 테스트
7. **마감 대응** — README + 데모 + 제출물 정리. 보안(키 폐기)은 늦어도 배포 전 처리.

---

## 9. 다음 액션 (착수)

- [ ] `allthestreet-agent-gateway` 스캐폴딩 생성
- [ ] DB read-only 접속 테스트 (신규 계정 or 임시 운영계정)
- [ ] `SpotInfo` 1건으로 GEO JSON-LD 프로토타입 출력 → 눈으로 검증
