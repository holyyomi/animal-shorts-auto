import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _get_drive_service():
    """Build Google Drive API service using service account credentials."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError("Install google-api-python-client: pip install google-api-python-client")

    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    sa_file = Path(sa_path)

    if not sa_file.exists():
        raise FileNotFoundError(
            f"\n[Drive 오류] service_account.json 파일을 찾을 수 없습니다: {sa_path}\n"
            "→ Google Cloud Console에서 서비스 계정 키를 발급받아 프로젝트 루트에 저장하거나,\n"
            "  .env 파일의 GOOGLE_SERVICE_ACCOUNT_JSON 경로를 확인하세요."
        )

    try:
        content = sa_file.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError("service_account.json이 비어 있습니다.")
        sa_data = json.loads(content)  # validate JSON
        client_email = sa_data.get("client_email", "unknown")
        logger.info(f"✔ Service account JSON 로드 성공: {sa_path}")
        logger.info(f"✔ 인증 계정(email): {client_email}")
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(
            f"\n[Drive 오류] service_account.json 파일이 유효하지 않습니다: {e}\n"
            "→ Google Cloud Console에서 올바른 서비스 계정 JSON 키 파일을 다시 발급받으세요."
        )

    scopes = ["https://www.googleapis.com/auth/drive.file"]
    creds = service_account.Credentials.from_service_account_file(sa_path, scopes=scopes)
    return build("drive", "v3", credentials=creds)


def _create_folder(service, name: str, parent_id: str) -> str:
    """Create a folder in Drive under parent_id. Returns new folder ID."""
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def _upload_file(service, file_path: Path, folder_id: str) -> str:
    """Upload a single file to a Drive folder. Returns uploaded file ID."""
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(file_path), resumable=True)
    metadata = {"name": file_path.name, "parents": [folder_id]}
    uploaded = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return uploaded["id"]


def upload_to_drive(run_id: str, files: list[Path], parent_folder_id: str) -> Optional[str]:
    """
    Create run_id folder under parent_folder_id, upload all files.
    Returns the created folder ID, or None on failure.
    """
    from app.utils import sanitize_drive_folder_id
    parent_folder_id = sanitize_drive_folder_id(parent_folder_id)

    if not parent_folder_id:
        logger.warning("GOOGLE_DRIVE_PARENT_FOLDER_ID not set, skipping Drive upload")
        return None

    masked_id = parent_folder_id[:5] + "***" + parent_folder_id[-4:] if len(parent_folder_id) > 10 else "***"
    logger.info(f"✔ Drive 업로드 준비 (Parent ID: {masked_id})")

    try:
        service = _get_drive_service()
        logger.info("✔ Drive API 연결 및 권한 인증 완료, 폴더 생성 시도 중...")
        folder_id = _create_folder(service, run_id, parent_folder_id)
        logger.info(f"✔ 런 폴더 생성 완료: {run_id} (ID={folder_id})")

        for f in files:
            if f.exists():
                file_id = _upload_file(service, f, folder_id)
                logger.info(f"✔ 업로드 성공: {f.name} (ID={file_id})")
            else:
                logger.warning(f"⚠ 업로드 실패 (파일 없음): {f}")

        return folder_id

    except Exception as e:
        error_msg = str(e)
        if "HttpError 404" in error_msg:
            logger.error(f"[Drive 폴더 접근 오류 404] Parent Folder ID가 잘못되었거나 공유 권한이 없습니다.")
            logger.error("→ 해결방법: 서비스 계정 이메일을 해당 드라이브 폴더에 '편집자' 권한으로 초대하세요.")
        elif "HttpError 403" in error_msg:
            logger.error(f"[Drive 권한/용량 오류 403] 서비스 계정의 저장소 용량이 초과되었거나 권한이 거부되었습니다.")
            logger.error("→ 해결방법: 서비스 계정의 할당량을 확인하거나 다른 계정을 사용하세요.")
        else:
            logger.error(f"[Drive 업로드 실패] {e}")
        
        logger.error(f"→ 파일은 로컬(data/output/{run_id})에 안전하게 저장되어 있습니다.")
        raise
