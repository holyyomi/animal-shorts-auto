import logging
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def setup_logger(name: str) -> logging.Logger:
    """Configure and return a module-level logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def get_next_run_id(output_dir: Path) -> str:
    """Return next zero-padded run ID (e.g. '0001', '0002')."""
    existing = (
        [int(p.name) for p in output_dir.iterdir() if p.is_dir() and p.name.isdigit()]
        if output_dir.exists()
        else []
    )
    return f"{max(existing, default=0) + 1:04d}"


def get_path(relative: str) -> Path:
    """Return absolute path relative to project root."""
    return BASE_DIR / relative


def sanitize_drive_folder_id(raw: str) -> str:
    """
    Extract pure Google Drive folder ID from any input format.

    Handles:
      - Full URL:  https://drive.google.com/drive/folders/1AbCdEfG?hl=ko
      - Short URL: https://drive.google.com/drive/folders/1AbCdEfG
      - Raw ID:    1AbCdEfGhIjKlMnOp
      - Empty / whitespace → returns ""
    """
    if not raw:
        return ""
    raw = raw.strip()

    # Extract from /folders/{id} pattern
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", raw)
    if m:
        return m.group(1)

    # Strip query-string / fragment if present, then return
    raw = re.split(r"[?&#]", raw)[0].strip("/").strip()

    # Validate: Drive IDs are typically 28–44 alphanumeric + _ + - chars
    if re.match(r"^[a-zA-Z0-9_-]{10,}$", raw):
        return raw

    return raw  # return as-is, let Drive API report the error

def load_used_assets() -> set[str]:
    """Load previously used asset IDs/names to avoid repetition."""
    record_file = get_path("data/used_assets.txt")
    if not record_file.exists():
        return set()
    with open(record_file, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_used_assets(assets: list[str]) -> None:
    """Save used asset IDs/names."""
    record_file = get_path("data/used_assets.txt")
    record_file.parent.mkdir(parents=True, exist_ok=True)
    with open(record_file, "a", encoding="utf-8") as f:
        for a in assets:
            f.write(f"{a}\n")
