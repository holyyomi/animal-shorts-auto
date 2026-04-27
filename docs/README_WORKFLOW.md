# Workflow Guide

## 처음 세팅 순서

1. **저장소 클론 후 의존성 설치**
   ```bash
   git clone <your-repo-url>
   cd video
   pip install -r requirements.txt
   ```

2. **FFmpeg 설치** (MoviePy 렌더링 필수)
   - Windows: https://ffmpeg.org/download.html → 환경변수 PATH 추가
   - Ubuntu: `sudo apt-get install ffmpeg imagemagick`

3. **API 키 발급**
   - Pexels: https://www.pexels.com/api/ (무료 가입 후 즉시 발급)
   - OpenRouter: https://openrouter.ai/ (무료 모델: `google/gemma-3-27b-it:free`)
   - OpenAI: https://platform.openai.com/api-keys (폴백용, 유료)
   - Google Drive: 서비스 계정 생성 → JSON 키 다운로드 → Drive 폴더 공유

4. **.env 파일 생성**
   ```bash
   cp .env.example .env
   # .env에 실제 키 값 입력
   ```

5. **(선택) 한국어 폰트 추가**
   ```
   assets/fonts/NanumGothicBold.ttf
   ```
   없으면 MoviePy 기본 폰트 사용 (자막 품질 저하 가능)

6. **(선택) BGM 추가**
   ```
   assets/music/bgm.mp3
   ```
   없으면 음소거 렌더링

---

## 로컬 테스트 순서

```bash
# 실행
python -m app.main

# 결과 확인
ls data/output/0001/
# → shorts_0001.mp4
# → upload_package.txt
# → meta.json
```

로그에서 확인할 항목:
- `Pexels returned N videos` — API 정상 동작
- `Selected: pexels_XXXXX.mp4` — 클립 선택 완료
- `Subtitles: [...]` — 자막 생성 완료
- `Rendered: data/output/0001/shorts_0001.mp4` — 렌더 완료
- `Uploaded shorts_0001.mp4` — Drive 업로드 완료

---

## GitHub Secrets 등록 목록

저장소 → Settings → Secrets and variables → Actions → New repository secret

| Secret 이름 | 값 |
|------------|---|
| `PEXELS_API_KEY` | Pexels API 키 |
| `OPENROUTER_API_KEY` | OpenRouter API 키 |
| `OPENAI_API_KEY` | OpenAI API 키 |
| `GOOGLE_DRIVE_PARENT_FOLDER_ID` | Drive 폴더 URL의 마지막 ID 부분 |
| `GOOGLE_SERVICE_ACCOUNT_B64` | service_account.json을 base64 인코딩한 값 |

**service_account.json → base64 변환 방법:**
```bash
# Linux/Mac
base64 -w 0 service_account.json

# Windows (PowerShell)
[Convert]::ToBase64String([IO.File]::ReadAllBytes("service_account.json"))
```

---

## GitHub Actions 실행 개념

```
[workflow_dispatch 클릭]
        ↓
[ubuntu-latest 환경 세팅]
        ↓
[Python 3.11 + FFmpeg + pip install]
        ↓
[Secrets → .env 주입 + service_account.json 복원]
        ↓
[python -m app.main 실행]
        ↓
[data/output/ → Artifacts 업로드 (7일)]
        ↓
[Google Drive에도 자동 저장]
```

---

## 문제 발생 시 점검 포인트

1. **로컬 실행 실패** → `docs/TROUBLESHOOTING.md` 참고
2. **Actions 실패** → Actions 탭 → 실패한 Step → 로그 확인
3. **Drive 업로드 안 됨** → `GOOGLE_DRIVE_PARENT_FOLDER_ID` 확인, 서비스 계정에 폴더 공유 여부 확인
4. **자막이 기본값** → OpenRouter/OpenAI 키 확인, 로그에서 LLM 오류 확인
