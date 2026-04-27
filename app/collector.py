import os
import time
import logging
from pathlib import Path
from typing import Optional

import requests
logger = logging.getLogger(__name__)

PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"


def search_animal_videos(query: str = "animals funny", per_page: int = 5) -> list[dict]:
    """Search Pexels for animal videos. Returns list of video metadata."""
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise EnvironmentError("PEXELS_API_KEY is not set. Check your .env file.")

    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": per_page, "orientation": "portrait"}

    for attempt in range(3):
        try:
            resp = requests.get(PEXELS_VIDEO_API, headers=headers, params=params, timeout=30)
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"Pexels rate limit, retrying in {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            logger.info(f"Pexels returned {len(videos)} videos for query='{query}'")
            return videos
        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"Pexels attempt {attempt + 1} failed: {e}, retrying in {wait}s")
            time.sleep(wait)

    raise RuntimeError("Pexels API failed after 3 attempts")


def download_video(video_meta: dict, dest_dir: Path) -> Optional[Path]:
    """Download the best-quality portrait video file from Pexels metadata."""
    files = video_meta.get("video_files", [])
    if not files:
        logger.warning("No video files found in metadata")
        return None

    # Prefer portrait orientation
    portrait = [f for f in files if f.get("width", 0) < f.get("height", 1)]
    candidates = portrait if portrait else files
    best = max(candidates, key=lambda f: f.get("width", 0) * f.get("height", 0))

    url = best.get("link")
    if not url:
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = dest_dir / f"pexels_{video_meta['id']}.mp4"

    if filename.exists():
        logger.info(f"Already downloaded: {filename.name}")
        return filename

    logger.info(f"Downloading {filename.name} ...")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    logger.info(f"Downloaded: {filename.name}")
    return filename


def collect(query: str, dest_dir: Path, count: int = 5) -> list[Path]:
    """Search and download animal videos. Returns list of local paths."""
    videos = search_animal_videos(query=query, per_page=count)

    # Fallback query if primary returns nothing
    if not videos:
        fallback = "animals"
        logger.warning(f"Query '{query}' returned 0 results, retrying with '{fallback}'")
        videos = search_animal_videos(query=fallback, per_page=count)

    paths = []
    for v in videos:
        p = download_video(v, dest_dir)
        if p:
            paths.append(p)
    return paths
