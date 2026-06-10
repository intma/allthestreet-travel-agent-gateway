# RECON — 시스템 정찰 결과

> AllTheStreet 기존 시스템 파악 기록 (2026-06-05).
> 신규 게이트웨이 설계의 근거 자료. 메인 진행상황은 `../PROGRESS.md`.

---

## GCP 프로젝트

| 프로젝트 | 역할 |
|---|---|
| `street-view-0315` | **소스코드 저장소(Cloud Source Repos) 보유** |
| `allthestreet-kmukbang` | 앱 백엔드: Firestore/Auth/FCM/분석. 서버 AI 로직 없음 |
| `allthestreet-7eb12` | 유사한 Firebase 백엔드 |
| `geomundo-b49c0`, `wys3-efdac` | 별개 |

확인된 사실: Cloud Run / Cloud Functions / Vertex AI 미사용. App Engine 배포 없음.
Storage 버킷 0개(해당 계정 범위). 즉 **서버 사이드 AI 에이전트는 GCP에 없었음** —
여행계획/추천은 앱 클라이언트 또는 사전 큐레이션 데이터.

## Cloud Source 저장소 (`street-view-0315`)

| 저장소 | 정체 |
|---|---|
| `mukbang-backend` | **Flask(Python) API 서버** = `api.allthestreet.com`. peewee ORM, SocketIO |
| `mukbang-app` | Vue 어드민 (`vue-element-admin` 템플릿). 모바일앱 아님 |
| `vue-front-new-allthestreet` | 신규 웹 프론트 (`korea.allthestreet.com`) |
| `new-all-the-street` | 신버전 통합 (미확인) |
| `mukbang-admin` | 관리자 SaaS (미확인) |
| `allthestreet` | 구버전/루트 (미확인) |

## 데이터베이스

- MySQL `mukbang` @ `34.64.228.95:3306` (GCP 호스팅).
- **외부 직접 접속 차단** (Cloud Shell에서 timeout=110). → 신규 서비스는 API 경유.
- 접속정보는 `models.py`에 평문 (보안 이슈, Secret Manager 대상).

## 데이터 소스 엔드포인트 (확정)

`GET api.allthestreet.com/api_mukbang/get_spot_data_admin?page=&pageSize=&searchKey=`

- `before_request`에서 Authorization 헤더가 **없으면 통과**(레거시앱 호환). → 인증 없이 read 가능.
- 반환 필드: spot_id, spot_name(원문/kr/en), spot_lat, spot_lng, spot_address(원문/kr/en),
  spot_google_place_id, spot_naver_place_id, spot_thumbnail_url, spot_detail, spot_relate_video,
  category_id, region_id, create_time.
- `spot_detail`은 **Google Places 원본 JSON 문자열** — geometry(좌표), opening_hours(요일별),
  formatted_phone_number, business_status 포함. → GEO/UCP 재료로 풍부.

## SpotInfo 모델 핵심 필드

spot_lat/lng(좌표), spot_google_place_id(Maps 앵커), spot_naver_place_id,
spot_address, spot_name(_kr), spot_detail(상세/FAQ 원천), spot_thumbnail_url,
spot_relate_video(Video-to-Place). → JSON-LD Place/LocalBusiness/Video 구현 충분.

## Gemini의 기존 용도 (오해 주의)

`scrap/gemini.py`(GeminiProcessor)는 **여행계획 에이전트가 아님**. 실제 역할은
SNS 숏폼 영상 설명 → 음식점명/위치/타임프레임 추출 → DB 적재(콘텐츠 수집 파이프라인).
모델 `gemini-2.0-flash`. **API 키 평문 하드코딩** (폐기 대상).

## 식별된 보안 이슈

| # | 항목 | 위치 |
|---|---|---|
| R1 | Gemini API 키 평문 | `scrap/gemini.py` |
| R2 | Google Places 키 평문 | `scrap/google.py` (self.api_key) |
| R3 | DB 접속정보 평문 | `models.py` |
| R4 | admin API 무인증 통과 | `main.py` before_request (우리에겐 유리하나 결함) |
| R5 | CORS 전체 허용 | `CORS(app)` |

신규 게이트웨이는 이 결함들을 반대로 — read-only, 키 서버측 보관, CORS 화이트리스트 —
구현하는 방향.
