# SCALABILITY — 확장 로드맵 (데모 → 멀티테넌트 SaaS)

> 메인 진행상황은 `../PROGRESS.md`. 이 문서는 **챌린지 이후** 외부 여행사가
> 가입·등록·분석하는 SaaS로 키울 때의 단계별 인프라 로드맵.
> 핵심 원칙: **챌린지엔 현재 구조(메모리 캐시 + min-instances 1)로 가고,
> 확장은 트래픽·사업자 수가 실제로 늘 때 단계적으로.** 미리 다 깔지 말 것.

---

## 목표 그림 (최종 SaaS 형태)

```
[Gemini·크롤러] ─┐
                 ├→ [게이트웨이 Cloud Run] ←→ [Redis 캐시] ←→ [Cloud SQL]
[사업자 프론트] ─→ [어드민 SaaS Cloud Run] ─┘              ↑
                         │                                 │
                    (등록) → [Pub/Sub] → 캐시무효화·GEO·sitemap 갱신
                         │
                    [BigQuery] ← 노출/트래픽 이벤트 (대시보드)
[Cloud Storage + CDN] ← 이미지·3D·숏폼
[Secret Manager] ← 키·DB암호    [Cloud Build → Artifact Registry] ← CI/CD
```

역할 분리:
- **게이트웨이** (읽기·공개, GEO/UCP/MCP) — Gemini·크롤러 대상. 무상태+공유캐시 → 0~N 자동확장.
- **어드민 SaaS API** (쓰기·인증, 가입·등록·대시보드) — 사업자 대상. 트래픽 패턴 다름 → 독립 배포.
- **사업자 프론트** (회원가입·상품등록·대시보드 UI).

---

## 현재 상태 (챌린지 시점)

- 단일 Cloud Run 서비스(게이트웨이), 읽기 전용. 기존 백엔드(api.allthestreet.com) 읽기.
- 캐시: **인스턴스 메모리** (spot/영상/상품 인덱스). `min-instances 1`로 유지,
  `--no-cpu-throttling`으로 백그라운드 빌드 안정화.
- 한계: 인스턴스 확장(N개) 시 각자 중복 캐싱·갱신 불일치. 쓰기/인증/테넌트 격리 없음.

---

## 단계별 로드맵

### 1단계 — 캐시 추상화 → Redis (확장성의 첫 분기점)
**문제:** 메모리 캐시는 인스턴스 종속 → autoscaling 시 중복·불일치.
**작업:**
1. **캐시 추상화** (코드 리팩터링, 동작 변화 없음):
   - `CacheBackend` 인터페이스(get/set/delete/list) 정의.
   - 현재 모듈 전역(`_SPOT_INDEX` 등)을 `MemoryCache` 구현으로 이전.
   - `repository.py`/`videos.py`/`products.py`가 인터페이스만 의존하게.
2. **Memorystore(Redis) 도입** → `RedisCache` 구현 추가, 환경변수로 토글.
   - 인덱스를 Redis에 공유 → 모든 인스턴스가 같은 캐시 참조.
   - `min-instances` 제약 해제 → **0~N 자동확장** 가능.
**효과:** 무상태 게이트웨이 + 공유 캐시 → 트래픽 따라 자유 확장.
**주의:** 1단계 코드 변경은 캐시 계층에 국한. 비즈니스 로직 불변.

### 2단계 — SaaS 분리 (쓰기·인증·멀티테넌시)
**문제:** 사업자 가입·등록·대시보드 = 쓰기 + 인증 + 테넌트 격리. 게이트웨이와 역할·트래픽 다름.
**작업:**
1. **어드민 SaaS API**를 별도 Cloud Run 서비스로 분리(게이트웨이와 독립 배포·확장).
2. **인증**: Identity Platform / Firebase Auth (사업자 계정, 소셜 로그인).
3. **Cloud SQL 멀티테넌트 스키마**:
   - 모든 사업자 데이터에 `partner_id` 컬럼 → 행 수준 격리(자기 것만 조회/수정).
   - 기존 DB엔 partner 개념 없음 → **새 테이블/소유권 모델 설계 필요** (BIZ_SERVICE.md 참조).
   - 연결: Cloud SQL connector + 연결 풀링. 읽기 늘면 **읽기 복제본**.
4. **사업자 프론트**: 회원가입 → 상품/서비스 등록(ProductExtra 폼) → 대시보드(노출·판매·정산).
**효과:** 외부 여행사가 셀프서비스로 등록·관리. 게이트웨이는 그 데이터를 읽어 노출.

### 3단계 — 등록 → 자동 연결 (이벤트 기반)
**문제:** "사업자가 등록하면 korea.allthestreet.com에 자동 연결"을 동기로 하면 느리고 결합도 높음.
**작업:**
1. **Pub/Sub**: 상품/장소 등록·수정 시 이벤트 발행.
2. 구독자가: 게이트웨이 **캐시 무효화**(해당 spot/상품만), GEO/sitemap 갱신,
   (선택) Google Search Console 색인 요청.
3. 등록은 즉시 응답, 반영은 비동기 → 빠르고 느슨한 결합.
**효과:** "등록 즉시 노출"을 안정적으로. 자동화 사슬 완성.

### 4단계 — 트래픽 분석 (대시보드)
**문제:** 노출 수·판매 수·트래픽 통계 필요(사업자 대시보드 + 올더스트릿 운영).
**작업:**
1. 게이트웨이가 요청/노출/클릭 이벤트를 **Cloud Logging → BigQuery** (또는 직접 적재).
2. 실시간 카운터는 Redis, 누적·집계 분석은 BigQuery.
3. 대시보드가 BigQuery 집계를 조회(또는 Looker Studio 연동).
**효과:** 사업자별 노출·전환 통계 → 유료화·정산 근거.

### 5단계 — 콘텐츠 전송 최적화
- **Cloud Storage + Cloud CDN**: 이미지·썸네일·3D·숏폼을 CDN으로 → 게이트웨이 부하↓, 전송 속도↑.
- 이미지 프록시(`/img`)도 CDN 캐싱 활용.

---

## 가로지르는 항목 (단계 무관, 조기 권장)

- **보안 (Track 3 평가 직결, 우선)**: 노출된 API 키(Gemini, Google) 폐기·재발급 →
  **Secret Manager** 이전 → Cloud Run 주입. DB 암호도 Secret Manager.
  `GOOGLE_MAPS_API_KEY`는 HTTP 리퍼러 제한.
- **CI/CD**: Cloud Build(git push) → Artifact Registry → Cloud Run 자동 배포.
- **관측성**: Cloud Monitoring(메모리·CPU·지연), 알림(메모리 80%↑ → 상향).
- **비용**: min-instances·CPU 상시할당은 크레딧($500) 내 여유. SaaS 단계에서
  autoscaling으로 전환되면 사용량 기반으로 최적화.

---

## 우선순위 요약

| 시점 | 할 것 | 안 할 것 |
|---|---|---|
| **챌린지(현재)** | 현 구조 유지, `--no-cpu-throttling`, 보안(키) | Redis·Pub/Sub·멀티테넌트 (복잡도↑, 마감 위협) |
| **챌린지 후 1** | 캐시 추상화 → Redis (autoscaling 해제) | — |
| **2** | SaaS 분리·인증·Cloud SQL 멀티테넌트·프론트 | — |
| **3** | Pub/Sub (등록→자동연결) | — |
| **4** | BigQuery (대시보드) | — |
| **5** | Cloud CDN | — |

**핵심:** 확장은 트래픽·사업자가 실제로 늘 때. 미리 다 깔면 복잡도·비용만 늘고
챌린지 마감을 위협함. 이 문서는 "그때가 오면 이 순서로" 가이드.
