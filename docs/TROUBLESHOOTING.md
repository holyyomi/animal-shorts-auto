# Troubleshooting

---

## Pexels API 실패

**원인**
- `PEXELS_API_KEY` 미설정 또는 잘못된 값
- 일일 요청 한도 초과 (무료: 200 req/hour)
- 네트워크 오류

**확인**
```bash
# .env에 키가 있는지
grep PEXELS_API_KEY .env

# 직접 테스트
curl -H "Authorization: YOUR_KEY" "https://api.pexels.com/videos/search?query=cat&per_page=1"
```

**해결**
- 키 재확인: https://www.pexels.com/api/
- 한도 초과 시 1시간 대기
- `collector.py`의 `search_animal_videos`에서 `per_page` 줄이기

---

## OpenRouter 실패

**원인**
- `OPENROUTER_API_KEY` 미설정
- 무료 모델 일시적 다운 (`google/gemma-3-27b-it:free`)
- 응답 JSON 파싱 실패

**확인**
```bash
# 로그에서 확인
# "OpenRouter attempt N failed: ..."
# "OpenRouter failed, falling back to OpenAI"
```

**해결**
- `config/settings.yaml`의 `openrouter_model`을 다른 무료 모델로 변경
  - 대안: `mistralai/mistral-7b-instruct:free`, `meta-llama/llama-3.2-3b-instruct:free`
- 키 재발급: https://openrouter.ai/keys
- OpenAI 폴백이 자동으로 동작함 — 키만 설정되어 있으면 OK

---

## OpenAI 폴백 실패

**원인**
- `OPENAI_API_KEY` 미설정 또는 크레딧 부족
- 모델명 오류

**확인**
```bash
# 로그에서
# "Both OpenRouter and OpenAI failed"
# → 기본 자막 템플릿 사용으로 자동 폴백됨
```

**해결**
- 키 확인: https://platform.openai.com/api-keys
- 크레딧 충전
- 두 LLM 모두 실패해도 파이프라인은 기본 자막으로 계속 동작

---

## MoviePy 렌더 실패

**원인**
- FFmpeg 미설치
- ImageMagick 미설치 (TextClip 사용 시 필요)
- 입력 클립 파일 손상
- 폰트 파일 불일치

**확인**
```bash
ffmpeg -version
convert --version  # ImageMagick
```

**해결**
- Windows: FFmpeg PATH 추가 확인
- Ubuntu: `sudo apt-get install ffmpeg imagemagick`
- ImageMagick 정책 오류 시:
  ```bash
  sudo nano /etc/ImageMagick-6/policy.xml
  # <policy domain="path" rights="none" pattern="@*"/> 주석 처리
  ```
- 폰트 없을 경우: `assets/fonts/`에 TTF 파일 추가 또는 `_find_font()` 반환값 None 허용 (이미 처리됨)

---

## Google Drive 업로드 실패

**원인**
- `service_account.json` 없음 또는 경로 오류
- 서비스 계정에 폴더 공유 권한 없음
- `GOOGLE_DRIVE_PARENT_FOLDER_ID` 오류

**확인**
```bash
# 로그에서
# "Service account file not found: service_account.json"
# "Drive upload failed: ..."

# 폴더 ID 확인: Drive 폴더 URL 마지막 부분
# https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp
# → ID: 1AbCdEfGhIjKlMnOp
```

**해결**
1. `service_account.json` 프로젝트 루트에 배치
2. Google Drive → 폴더 → 공유 → 서비스 계정 이메일에 **편집자** 권한 부여
3. `.env`의 `GOOGLE_DRIVE_PARENT_FOLDER_ID` 재확인
- Drive 업로드 실패 시 로컬 `data/output/`에는 정상 저장됨

---

## GitHub Actions 실행 실패

**원인**
- Secrets 미등록
- `service_account.json` base64 인코딩 오류
- FFmpeg/ImageMagick 설치 step 실패

**확인**
- Actions 탭 → 실패한 job → 각 Step 클릭 → 로그 확인

**해결**
- Secrets 재확인: Settings → Secrets → 5개 모두 등록 여부
- base64 재생성:
  ```bash
  base64 -w 0 service_account.json  # Linux
  ```
- `generate-video.yml`의 apt-get step 로그 확인
- 로컬에서 정상 동작 확인 후 Actions 재실행
