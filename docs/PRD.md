# PRD — Animal Shorts Auto Builder

## 목표

Pexels 동물 영상 + LLM 한국어 자막을 조합하여, MoviePy로 15초 9:16 쇼츠를 자동 생성하고 Google Drive에 저장한다.
1회 실행 = 영상 1개 생성. 품질이 마음에 들지 않으면 재실행.

---

## 핵심 기능

| 기능 | 설명 |
|------|------|
| 영상 수집 | Pexels API로 동물 관련 세로 영상 검색 및 다운로드 |
| 클립 선택 | 15초 이상 클립 중 랜덤 선택 |
| 자막 생성 | OpenRouter 무료 모델로 웃긴 한국어 자막 4줄 이하 생성 |
| 영상 렌더 | MoviePy로 9:16 crop + 자막 오버레이 + (선택) BGM |
| 패키지 생성 | 6개 플랫폼별 제목/본문/해시태그 LLM 생성 |
| Drive 저장 | 순번 폴더(0001, 0002...) 생성 후 영상 + txt 저장 |

---

## 입력 / 출력

**입력:**
- `.env` 파일 (API 키)
- `config/settings.yaml` (설정)
- `config/prompts.yaml` (LLM 프롬프트)
- (선택) `assets/fonts/`, `assets/music/`

**출력:**
```
data/output/{NNNN}/
├── shorts_{NNNN}.mp4
├── upload_package.txt
└── meta.json
```
Google Drive 지정 폴더에도 동일 파일 업로드.

---

## 자동화 범위

| 항목 | 자동화 여부 |
|------|------------|
| 영상 검색/다운로드 | ✅ |
| 자막 생성 | ✅ |
| 영상 렌더링 | ✅ |
| 업로드 패키지 생성 | ✅ |
| Google Drive 저장 | ✅ |
| SNS 업로드 | ❌ (수동 — 업로드 패키지만 제공) |

---

## 플랫폼

- 유튜브 쇼츠
- 틱톡
- 네이버 클립
- 릴스 (Instagram Reels)
- 셀러비
- 카카오

---

## 제약 조건

1. CSV 파일 사용 금지
2. CapCut / GUI 편집기 의존 금지
3. MoviePy 기반 렌더링만 사용
4. `.env` / `service_account.json` 하드코딩 금지
5. `service_account.json` 저장소 커밋 금지
6. `python -m app.main` 단일 커맨드로 실행 가능
7. 1회 실행 = 결과물 1개

---

## 폴백 전략

| 실패 상황 | 폴백 동작 |
|----------|----------|
| OpenRouter 실패 | OpenAI로 자동 전환 |
| OpenAI 실패 | 기본 자막 템플릿 사용 |
| 패키지 LLM 실패 | 기본 패키지 템플릿 사용 |
| BGM 없음 | 음소거 렌더링 |
| 폰트 없음 | MoviePy 기본 폰트 사용 |
| Drive 업로드 실패 | 로컬 저장만 완료, 경고 로그 출력 |

모든 폴백 후에도 파이프라인이 중단되지 않도록 설계.

---

## MVP 범위

**포함:**
- Pexels API 수집 및 다운로드
- LLM 자막 생성 (OpenRouter → OpenAI 폴백)
- MoviePy 9:16 crop + 자막 렌더링
- upload_package.txt 생성
- Google Drive 업로드
- GitHub Actions workflow_dispatch 실행

**미포함 (이후 단계):**
- 자동 SNS 업로드
- 영상 품질 자동 평가
- 다국어 자막
- 배경 음악 자동 생성
- 썸네일 자동 생성
