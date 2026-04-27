# Animal Shorts Auto Builder

Pexels 동물 영상 + LLM 자막 + MoviePy 렌더링으로 **15초 9:16 쇼츠 1개**를 자동 생성하는 Python 자동화 프로젝트.
GitHub Actions에서 수동 또는 스케줄 실행 가능.

---

## 폴더 구조

```
video/
├── .github/workflows/generate-video.yml  # GitHub Actions 워크플로
├── app/
│   ├── main.py            # 파이프라인 진입점
│   ├── collector.py       # Pexels 영상 수집
│   ├── clip_selector.py   # 클립 선택
│   ├── subtitle_engine.py # LLM 자막 생성
│   ├── render_engine.py   # MoviePy 렌더링
│   ├── package_writer.py  # upload_package.txt + meta.json 저장
│   ├── drive_uploader.py  # Google Drive 업로드
│   ├── llm_router.py      # OpenRouter → OpenAI 폴백
│   └── utils.py           # 공통 유틸
├── assets/
│   ├── fonts/             # 한국어 폰트 (.ttf/.otf) — 없어도 동작
│   ├── logos/             # 로고 파일 (선택)
│   └── music/             # BGM 파일 (.mp3/.wav) — 없어도 동작
├── config/
│   ├── settings.yaml      # 프로젝트 설정
│   └── prompts.yaml       # LLM 프롬프트 템플릿
├── data/
│   ├── input/             # 수동 입력용 (현재 미사용)
│   ├── temp/              # 다운로드 임시 파일
│   ├── output/            # 최종 결과물 (run_id별 폴더)
│   └── logs/              # 로그 파일 (선택)
├── docs/
│   ├── PRD.md
│   ├── README_WORKFLOW.md
│   └── TROUBLESHOOTING.md
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## 필요한 API 키

| 키 이름 | 용도 | 무료 여부 |
|---------|------|----------|
| `PEXELS_API_KEY` | 동물 영상 검색/다운로드 | 무료 |
| `OPENROUTER_API_KEY` | LLM 자막/패키지 생성 (1순위) | 무료 모델 있음 |
| `OPENAI_API_KEY` | LLM 폴백 (2순위) | 유료 |
| `GOOGLE_DRIVE_PARENT_FOLDER_ID` | 결과물 저장 폴더 ID | 무료 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Drive 인증 (파일 경로) | 무료 |

---

## 로컬 실행

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. .env 파일 생성
cp .env.example .env
# .env 파일에 실제 API 키 입력

# 3. (선택) assets/fonts/ 에 한국어 TTF 폰트 추가
# 예: NanumGothicBold.ttf

# 4. 실행
python -m app.main
```

**결과물:** `data/output/0001/` 폴더에 생성
- `shorts_0001.mp4`
- `upload_package.txt`
- `meta.json`

---

## GitHub Actions 실행

1. 저장소 → **Settings → Secrets → Actions**에 아래 값 등록:
   - `PEXELS_API_KEY`
   - `OPENROUTER_API_KEY`
   - `OPENAI_API_KEY`
   - `GOOGLE_DRIVE_PARENT_FOLDER_ID`
   - `GOOGLE_SERVICE_ACCOUNT_B64` (service_account.json을 base64 인코딩한 값)

2. **Actions → Generate Animal Short → Run workflow** 클릭

3. 실행 완료 후 Artifacts에서 결과물 다운로드 (7일 보관)

---

## 결과물 예시

```
data/output/0001/
├── shorts_0001.mp4        # 15초 9:16 쇼츠 영상
├── upload_package.txt     # 플랫폼별 제목/본문/해시태그 (복붙용)
└── meta.json              # 실행 메타데이터
```

`upload_package.txt` 형식:
```
[유튜브 쇼츠]
강아지가 갑자기 ㅋㅋ
이 영상 다시 보고 또 웃었다
#강아지 #웃긴동물 #쇼츠

[틱톡]
...
```

---

## 보안 주의사항

> ⚠️ `.env`와 `service_account.json`은 **절대 Git에 커밋하지 마세요.**
> `.gitignore`에 포함되어 있으나, push 전에 반드시 직접 확인하세요.

- GitHub Actions에서는 Secrets를 통해 런타임에만 주입됩니다.
- `service_account.json`은 base64 인코딩 후 Secret으로 등록하세요.
