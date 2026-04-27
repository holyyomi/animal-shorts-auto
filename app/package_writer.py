import json
import logging
from pathlib import Path

from app.llm_router import call_llm

logger = logging.getLogger(__name__)

# Per-template fallback title style
_DEFAULT_TITLES = {
    "office_relatable": "이 눈빛 나잖아",
    "cute_irony":       "집사 무시하는 눈빛",
    "wild_contrast":    "이 짤 실물이다",
}


def _default_package(platforms: list[str], template_type: str = "office_relatable") -> dict:
    title = _DEFAULT_TITLES.get(template_type, "이 눈빛 나잖아")
    result = {}
    for platform in platforms:
        result[platform] = {
            "title": title,
            "body": "동물들의 예상치 못한 행동 모음! 보다가 공감 참기 불가 🐾",
            "hashtags": "#동물 #웃긴동물 #쇼츠 #동물영상 #귀여운동물",
        }
    return result


def _parse_package(raw: str, platforms: list[str], template_type: str) -> dict:
    try:
        text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning(f"Could not parse package JSON: {e}")
    return _default_package(platforms, template_type)


def generate_package(theme: str, description: str, settings: dict, prompts: dict) -> dict:
    """Generate platform-specific upload packages via LLM."""
    platforms: list[str]    = settings.get("platforms", [])
    template_type: str      = settings.get("project", {}).get("template_type", "office_relatable")
    template: str           = prompts.get("package_prompt", "")

    if template and platforms:
        prompt = (
            template
            .replace("{platforms}", ", ".join(platforms))
            .replace("{theme}", theme)
            .replace("{description}", description)
            .replace("{template_type}", template_type)
        )
        raw = call_llm(prompt, settings)
        if raw:
            return _parse_package(raw, platforms, template_type)

    logger.warning("Using default upload package")
    return _default_package(platforms, template_type)


def save_package(package: dict, output_dir: Path, run_id: str, meta: dict) -> tuple[Path, Path]:
    """
    Save upload_package.txt and meta.json to output_dir.
    Format: [플랫폼명] / 제목 / 본문 / 해시태그 — no labels, copy-paste ready.
    Returns (txt_path, meta_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    txt_lines: list[str] = []
    for platform, content in package.items():
        txt_lines.append(f"[{platform}]")
        txt_lines.append(content.get("title", ""))
        txt_lines.append(content.get("body", ""))
        txt_lines.append(content.get("hashtags", ""))
        txt_lines.append("")  # blank separator

    txt_path = output_dir / "upload_package.txt"
    txt_path.write_text("\n".join(txt_lines).strip(), encoding="utf-8")
    logger.info(f"Saved: {txt_path}")

    meta_path = output_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Saved: {meta_path}")

    return txt_path, meta_path
