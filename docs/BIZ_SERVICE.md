# BIZ_SERVICE — 사업자 서비스(C) 설계 메모

> `biz.metaxtreet.com` — 외부 사업자가 자기 장소·상품을 등록·관리하고
> 올더스트릿 GEO/UCP/MCP 인프라로 노출되게 하는 서비스.
> **구축은 챌린지(6/12) 이후.** 이 문서는 그때 바로 착수하기 위한 발견·설계 기록.
> 메인 로드맵은 `../PROGRESS.md`.

---

## 목표 (사업자 서비스)

- 신규: **회원가입/로그인, 대시보드**
- 기존 기능 활용: **장소 관리, 유튜브 관리, 상품 관리**
- 향후: 메시지 관리, 매출/정산

기존 내부 관리자 `admin.allthestreet.kr`(= `mukbang-admin`)의 메뉴/기능을 가져와
**외부 사업자용**으로 변형하는 방향.

## 정찰로 확인된 사실 (2026-06-05)

### 재사용 가능한 자산 (mukbang-admin, vue-element-admin 기반)
- 로그인 화면: `src/views/login/` (index + auth-redirect) — 존재
- 대시보드/차트: `src/views/dashboard/`, `src/views/charts/` — 존재
- 권한 시스템: vue-element-admin 내장(role 기반, 라우터에 주석으로 존재)
- 관리 화면: `src/views/mukbang-admin/` (spot.vue, video.vue, sns.vue, region.vue,
  notice.vue, pay.vue, auto-run.vue, temp-video.vue) + `src/views/regist/`
  (spot, youtube, region, branch-point 등록 화면)
- API 정의: `src/api/` (mukbang.js, allthestreet.js, google.js, youtube.js,
  user.js, role.js)
- 백엔드 연결: production `VUE_APP_MUKBANG_API=/api_mukbang` → `mukbang-backend`(Flask)

### 가져올 메뉴 / 제외할 메뉴
- 가져옴: 장소(spot), 유튜브(youtube/video), 상품(상품 백엔드 확정 후)
- 제외(내부 전용): 분기점등록, region, auto-run(자동수집), temp-video, notice,
  charts/components 데모

## ⚠️ 핵심 과제 1 — 데이터 소유 모델 부재

`mukbang` DB 어디에도 **"이 장소·상품을 어느 사업자가 등록했는가"** 가 없다.
- `SpotInfo`: owner/partner/user_id 없음
- `PrepaidCard.card_user_id`, `Comments.user_id`, `FavInfo.user_id`: 일반 이용자용,
  사업자 소유와 무관
- 사업자(회원) 테이블 자체가 없음

→ 외부 사업자가 "자기 것만" 보려면 소유 모델을 **신설**해야 함:
1. `Partner`(사업자) 테이블 신설 — 회원가입 정보(이메일/전화/국가/사업자명/권한)
2. `SpotInfo`·상품 테이블에 `partner_id` 컬럼 추가
3. API에 `WHERE partner_id = 로그인사업자` 필터
4. 기존 내부 데이터는 `partner_id = NULL`(올더스트릿 직영)로 유지

이는 **운영 DB를 변경하는 write 작업** — 신중한 설계·마이그레이션 필요.
(게이트웨이가 read-only였던 것과 대조적)

## ⚠️ 핵심 과제 2 — 상품(Product) 백엔드 위치 미확정

PDF의 상품관리 화면(상품 추가·ProductExtra·FAQ·다국어 가격·kkday 링크)에
대응하는 테이블이 `mukbang` DB에 **없음**:
- `PrepaidCard`(prepaid_card_info): 선불카드 발급 정도
- `PayInfo`: 이미 발생한 주문/결제 기록(구매자 주소·수량·금액)
- `mukbang-admin/src/api`에 product 관련 함수 없음

→ 상품관리 화면이 보던 백엔드/DB가 별도일 가능성 높음
  (예: 별도 `product_info`/`schema_json` 테이블 보유 구성).
**챌린지 이후 착수 시 첫 작업 = 상품 데이터가 사는 위치 확정.**
확인 경로 후보: `new-all-the-street`, `allthestreet` 저장소, admin의 다른 환경설정,
또는 `admin.allthestreet.kr/saas/ucpproduct` 가 붙는 실제 API.

## 추가 보안 발견

- `mukbang-admin/.env`(production)에 Google API 키 평문 노출
  (`AIzaSy***REDACTED***`). 폐기·재발급 대상.

## 구축 시 권장 순서 (이후)

1. 상품 백엔드 위치 확정 + 스키마 파악
2. 데이터 소유 모델 설계 (Partner 테이블 + partner_id + 마이그레이션 계획)
3. 소유자 필터를 적용한 사업자용 API 계층 (기존 admin API 재사용 + 필터)
4. mukbang-admin 복제 → 사업자용 개조(메뉴 정리, 회원가입/약관, 소유자 스코프)
5. 대시보드 위젯(노출·판매), 이후 메시지·정산

## 미결정 사항

- 기존 `mukbang-admin` 복제 후 개조 vs 신규 프로젝트로 화면·API 이식
- 사업자 인증 방식(자체 회원 vs 소셜/Auth)
- 등록 데이터 검수(승인) 워크플로 필요 여부 (품질 관리)
- 게이트웨이(UCP/GEO/MCP)와의 연결: 사업자 등록 → 즉시 노출 vs 검수 후 노출

## 도메인 / URL 전략 (계획 — 챌린지 후 C단계)

**현재(챌린지):** 게이트웨이 = `https://allthestreet-agent-gateway-rfic5mxz6a-du.a.run.app`,
페이지 경로 `/p/{spot_id}`. 이 URL·경로 유지. (안정성·GEO 색인 보존, 도메인 연결은
시간·검증 부담이라 마감 후로)

**계획(C단계) — 역할별 도메인 분리:**
- **공개 게이트웨이(Gemini·크롤러용)**: `korea.allthestreet.com/p/{id}`
  (또는 `gateway.allthestreet.com`). 이미 콘텐츠 서비스 도메인이 있고 PDF의 연결
  URL도 `korea.allthestreet.com/[id]` 형식이라 통합이 자연스러움. 경로는 `/p/{id}`
  그대로 두고 **도메인만 앞에** 붙임(`/agent/` 등 중간 경로 불필요).
- **사업자 서비스**: `biz.metaxtreet.com` — 가입·상품등록·대시보드. 여기서
  "내 장소가 어떻게 보이나" **미리보기**는 게이트웨이 페이지를 링크/iframe으로
  띄우면 됨(별도 URL 구조 변경 불필요).

**원칙:** 공개=allthestreet 도메인, 사업자관리=metaxtreet 도메인으로 분리. 미리보기는
URL 구조와 무관하게 링크로 해결. 커스텀 도메인 연결 시 `PUBLIC_BASE_URL` 갱신 +
JSON-LD/sitemap/UCP feed 링크 재검증 필요(이때만 URL 변경).
