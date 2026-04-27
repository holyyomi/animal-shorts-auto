"""
Animal Shorts Auto Builder — Pipeline Entry Point
Run: python -m app.main
"""
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app.utils import setup_logger, get_next_run_id, get_path, BASE_DIR
from app.collector import collect
from app.clip_selector import select_clips
from app.subtitle_engine import generate_subtitles
from app.render_engine import render_video
from app.package_writer import generate_package, save_package
from app.drive_uploader import upload_to_drive

# Always load .env from project root, regardless of CWD
load_dotenv(dotenv_path=BASE_DIR / ".env")
logger = setup_logger(__name__)


def load_config() -> tuple[dict, dict]:
    """Load settings.yaml and prompts.yaml from config/."""
    settings_path = get_path("config/settings.yaml")
    prompts_path = get_path("config/prompts.yaml")

    if not settings_path.exists():
        logger.error(f"settings.yaml not found at {settings_path}")
        sys.exit(1)

    with open(settings_path, encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    prompts: dict = {}
    if prompts_path.exists():
        with open(prompts_path, encoding="utf-8") as f:
            prompts = yaml.safe_load(f) or {}
    else:
        logger.warning("prompts.yaml not found, will use default templates")

    # Allow env override for Drive folder
    env_folder = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID")
    if env_folder:
        settings.setdefault("drive", {})["parent_folder_id"] = env_folder

    return settings, prompts


def main() -> None:
    logger.info("=== Animal Shorts Auto Builder START ===")

    # 1. Load config
    settings, prompts = load_config()
    duration: float = float(settings.get("video", {}).get("duration", 11.0))

    # 2. Generate run_id (0001, 0002, ...)
    output_base = get_path("data/output")
    run_id = get_next_run_id(output_base)
    run_output_dir = output_base / run_id
    logger.info(f"Run ID: {run_id}")

    # 3. Collect animal clips from Pexels
    temp_dir = get_path("data/temp") / run_id
    logger.info("Collecting animal videos from Pexels...")
    try:
        clip_paths = collect(query="animals funny", dest_dir=temp_dir, count=5)
    except Exception as e:
        logger.exception(f"Video collection failed: {e}")
        sys.exit(1)

    if not clip_paths:
        logger.error("No clips downloaded. Check PEXELS_API_KEY and network.")
        sys.exit(1)

    # 4. Select story segments (multiple clips)
    logger.info("Selecting story segments...")
    selected_clips = select_clips(clip_paths, target_duration=duration)
    if not selected_clips:
        logger.error("Clip selection failed. Please check the logs above for more details.")
        sys.exit(1)
        
    # Mark as used
    from app.utils import save_used_assets
    save_used_assets([c.name for c in selected_clips])

    # 5. Generate subtitles and upload package via LLM
    description = f"A funny animal short story with clips: {', '.join([c.stem for c in selected_clips])}"
    theme = "동물 스토리 숏폼"

    logger.info("Generating subtitles...")
    subtitles = generate_subtitles(description, settings, prompts, debug_dir=run_output_dir)
    logger.info(f"Subtitles: {subtitles}")

    logger.info("Generating upload package...")
    package = generate_package(theme, description, settings, prompts)

    # 6. Render video with MoviePy
    output_video = run_output_dir / f"shorts_{run_id}.mp4"
    logger.info(f"Rendering video → {output_video}")
    rendered = render_video(selected_clips, subtitles, output_video, settings, covers_dir=run_output_dir)

    if not rendered:
        logger.error("Video render failed. Check MoviePy and FFmpeg installation, or check previous error logs.")
        sys.exit(1)

    # 7. Save upload_package.txt + meta.json
    meta = {
        "run_id": run_id,
        "source_clips": [c.name for c in selected_clips],
        "subtitles": subtitles,
        "description": description,
        "theme": theme,
        "platforms": settings.get("platforms", []),
    }
    txt_path, meta_path = save_package(package, run_output_dir, run_id, meta)

    # 8. Upload to Google Drive
    parent_folder_id: str = settings.get("drive", {}).get("parent_folder_id", "")
    if parent_folder_id:
        logger.info("Uploading to Google Drive...")
        upload_to_drive(run_id, [rendered, txt_path], parent_folder_id)
    else:
        logger.info("Drive upload skipped (GOOGLE_DRIVE_PARENT_FOLDER_ID not set)")

    logger.info(f"=== DONE | Run ID: {run_id} | Output: {run_output_dir} ===")


if __name__ == "__main__":
    main()
