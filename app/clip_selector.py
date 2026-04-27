import logging
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def select_clips(candidates: list[Path], target_duration: float = 12.0) -> list[Path]:
    """
    Select 1~2 clips from candidates to build a story segment.
    Avoids recently used clips to ensure freshness.
    """
    from app.utils import load_used_assets
    used = load_used_assets()
    
    if not candidates:
        logger.error("No candidate clips to select from")
        return []

    try:
        from moviepy import VideoFileClip
        from app.llm_router import call_llm
        import json

        def evaluate_clip(clip_path: Path) -> dict:
            """Evaluate video quality and story score using LLM based on its filename proxy."""
            prompt = f"""
You are a video editor evaluating a raw clip for a funny animal short.
The clip is named: {clip_path.stem}

Evaluate the clip based on its name and potential.
1. Story Score (0-100) based on:
   - 첫 2초 궁금증 (Hook potential)
   - 행동 변화 (Action shift)
   - 반응/여운 (Reaction/Aftermath)
   - 루프 적합성 (Loop friendly)
   - 피사체 크기 (Subject size)
   - 배경 단순성 (Background simplicity)
2. Filter criteria (Boolean, true if severe issue):
   - no_movement: 움직임 거의 없음
   - subject_too_small: 피사체 너무 작음
   - messy_bg: 배경 너무 복잡함
   - no_story: 이야기 구조 안나옴

Output MUST be JSON:
{{
  "story_score": 85,
  "filter_fail": false,
  "filter_reason": "Pass",
  "score_breakdown": "Hook: High, Action: Good"
}}
"""
            raw = call_llm(prompt, {})
            if raw:
                try:
                    text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                    return json.loads(text)
                except Exception:
                    pass
            return {"story_score": 70, "filter_fail": False, "filter_reason": "LLM Error", "score_breakdown": "N/A"}

        valid: list[tuple[Path, float, dict]] = []
        for path in candidates:
            # Skip if already used
            if path.name in used:
                continue
                
            try:
                clip = VideoFileClip(str(path))
                duration = clip.duration
                clip.close()
                if duration >= 2.0:
                    eval_data = evaluate_clip(path)
                    # 4. source quality filter
                    if eval_data.get("filter_fail", False):
                        logger.info(f"Filtered out {path.name}: {eval_data.get('filter_reason')}")
                        continue
                    valid.append((path, duration, eval_data))
            except Exception as e:
                logger.warning(f"Could not read {path.name}: {e}")

        # If not enough unused valid clips, fallback
        if len(valid) < 2:
            logger.warning("Not enough fresh clips passing filters, reusing some...")
            for path in candidates:
                if path.name in used and path not in [v[0] for v in valid]:
                    try:
                        clip = VideoFileClip(str(path))
                        duration = clip.duration
                        clip.close()
                        if duration >= 2.0:
                            eval_data = evaluate_clip(path)
                            valid.append((path, duration, eval_data))
                    except:
                        pass
        
        if not valid:
            logger.error("No readable clips found.")
            return []

        # Sort by story score
        valid.sort(key=lambda x: x[2].get("story_score", 0), reverse=True)
        
        selected = []
        pool = [p for p, d, e in valid]
        
        # Pick 1 or 2 highest scored ones.
        num_to_pick = random.choice([1, 2])
        num_to_pick = min(len(pool), num_to_pick)
        if num_to_pick == 0:
            return []
            
        selected = pool[:num_to_pick]
        
        logger.info(f"Selected {len(selected)} clips for story segments.")
        return selected

    except ImportError:
        logger.warning("moviepy not available, selecting random clips")
        random.shuffle(candidates)
        return candidates[:min(len(candidates), 2)]
