# GitHub 제출 가이드 — 비공개 레포 + 심사자 접근

> 목표: 코드를 **심사자만** 볼 수 있게 하되(비공개 레포), **읽을 수는 있게**(평가 가능).
> ⚠️ "암호화/난독화"는 하지 않습니다 — 심사자가 코드를 읽어 평가해야 하므로,
>    암호화하면 평가 불가 → 제출 무효가 됩니다. 올바른 방법은 "비공개 + 접근 초대"입니다.

---

## 0. 두 가지 ZIP 중 무엇을 올리나

- **`allthestreet-gateway-REPO.zip`** ← **이걸 GitHub에 올리세요** (심사용)
  - 내부 노트(PROGRESS.md, docs/BIZ_SERVICE.md) 제외
  - GCP 프로젝트 ID/번호, 실제 서비스 URL → 플레이스홀더 처리
  - 코드·README·ARCHITECTURE·DEPLOY 포함 (심사자가 읽고 평가 가능)
- `allthestreet-agent-gateway-final.zip` = 본인 보관용 전체 (올리지 마세요)

---

## 1. 비공개 레포 만들고 코드 올리기

GitHub 웹에서 **New repository** → 이름(예: `allthestreet-travel-agent-gateway`)
→ **Private** 선택 → Create.

로컬에서 (REPO.zip 푼 폴더에서):
```bash
git init
git add .
git commit -m "AllTheStreet Travel Agent Gateway — Google AI Agents Challenge (Track 1)"
git branch -M main
git remote add origin https://github.com/<your-id>/allthestreet-travel-agent-gateway.git
git push -u origin main
```
> `.gitignore`가 이미 있어 `.env`·`__pycache__`·`*.zip`은 자동 제외됩니다.

---

## 2. 심사자만 접근하게 — 두 방법 중 하나

**방법 A (권장): Devpost가 지정한 심사자 계정을 Collaborator로 초대**
- 레포 → Settings → Collaborators → Add people
- Devpost 챌린지 Rules에 적힌 **심사자 GitHub 핸들/이메일**을 추가
- (Rules에 "심사자를 collaborator로 초대하라"는 안내가 보통 있습니다. 그대로 따르세요.)

**방법 B: Devpost Rules가 "공개 레포"를 요구하면**
- 그땐 Private 대신 Public으로. (단 아래 3번 점검을 반드시 끝낸 뒤)

⚠️ **확인 필요**: Devpost 챌린지 페이지의 **Rules / Submission requirements**에서
   "코드를 어떻게 제출/접근하게 하라"는 지침을 먼저 확인하세요. 그게 최종 기준입니다.

---

## 3. 올리기 전 마지막 점검 (민감정보) — 이미 처리했지만 재확인

이 REPO.zip은 아래가 이미 처리되어 있습니다:
- ✅ 코드(.py)에 하드코딩된 키·비밀번호 없음 (모두 환경변수/Secret Manager)
- ✅ `.gitignore`로 `.env`·시크릿·캐시 제외
- ✅ docs의 키 흔적 마스킹(`***REDACTED***`)
- ✅ GCP 프로젝트 ID/번호, 서비스 URL → 플레이스홀더(`YOUR_PROJECT_ID` 등)
- ✅ 내부 노트(PROGRESS.md, BIZ_SERVICE.md) 제외

직접 한 번 더 보고 싶으면:
```bash
grep -rn "AIza\|sk-\|password\|qwer123" . --include="*.py" --include="*.md"
# 아무것도 안 나오면 OK
```

---

## 4. Devpost "Code" 칸에 넣을 링크
```
https://github.com/<your-id>/allthestreet-travel-agent-gateway
```
비공개면 심사자 초대를 꼭 먼저 끝내세요(안 그러면 "접근 불가"로 평가 못 받음).

---

## 참고: 왜 암호화가 아니라 비공개인가
- 심사 기준은 "코드를 보고 어떻게 만들었는지 평가"입니다 (MCP를 제대로 썼나 등).
- 암호화/난독화하면 심사자도 못 읽음 → 평가 불가 → 감점 또는 무효.
- "남에게 안 보이게"의 정답은 **비공개 레포 + 심사자만 초대**입니다.
- 비밀(키 등)은 코드에서 빼서 Secret Manager/환경변수로 — 이건 이미 되어 있습니다.
