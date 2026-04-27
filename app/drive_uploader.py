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
        json.loads(content)  # validate JSON
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

    try:
        service = _get_drive_service()
        folder_id = _create_folder(service, run_id, parent_folder_id)
        logger.info(f"Created Drive folder: {run_id} (id={folder_id})")

        for f in files:
            if f.exists():
                file_id = _upload_file(service, f, folder_id)
                logger.info(f"Uploaded {f.name} (id={file_id})")
            else:
                logger.warning(f"File not found, skipping upload: {f}")

        return folder_id

    except Exception as e:
        logger.error(f"[구글 드라이브 업로드 실패] {e}\n→ 파일은 로컬(data/output/{run_id})에 안전하게 저장되어 있습니다.")
        return None
