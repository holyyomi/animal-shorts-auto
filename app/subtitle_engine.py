import json
import logging
from pathlib import Path

from app.llm_router import call_llm

logger = logging.getLogger(__name__)

# Fallback subtitles
_DEFAULTS = [
    "저기요\n지금 뭐하심?",
    "상상도\n못한 전개",
    "이 상황을\n어떻게 하지",
    "결국\n이렇게 됨 ㅋㅋ",
]

# Hook & Ending Libraries
HOOK_LIBRARY = [
    "질문형: 지금 뭐하는 거지?",
    "오해형: 이거 나만 이상해?",
    "반전형: 예상치 못한 전개",
    "관계성: 둘이 왜 저래ㅋㅋ",
    "직장인: 출근 5분 전 내 모습",
]

ENDING_LIBRARY = [
    "이걸 또 보게 되네",
    "이래서 계속 봄",
    "다시 봐도 어이없음",
    "결국 이렇게 됨ㅋㅋ",
    "반복 재생 중",
]

def generate_subtitles(description: str, settings: dict, prompts: dict, debug_dir: Path = None) -> list[str]:
    """
    Two-step subtitle generation:
    1. Extract fact-based scene summary.
    2. Generate subtitle candidates based ONLY on the scene summary.
    Saves debug JSONs if debug_dir is provided.
    """
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Extract Scene Summary ──
    scene_summary_prompt = f"""
You are an expert video analyst. Analyze the following video description and extract a factual scene summary.
Do NOT invent actions that are not described.

Video description: {description}

Extract the following information:
1. animal_type: 동물 종류
2. animal_count: 화면에 몇 마리 나오는지
3. relative_size: 각 동물의 상대적 크기
4. main_action: 주요 행동
5. movement_change: 움직임 변화가 있는지
6. funny_points: 표정/자세/구도에서 웃긴 포인트가 무엇인지
7. twist_element: 마지막에 반전 요소가 있는지

Output MUST be a valid JSON object with the keys:
"animal_type", "animal_count", "relative_size", "main_action", "movement_change", "funny_points", "twist_element".
"""
    raw_summary = call_llm(scene_summary_prompt, settings)
    scene_summary_data = {}
    
    if raw_summary:
        try:
            text = raw_summary.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            scene_summary_data = json.loads(text)
            
            if debug_dir:
                summary_path = debug_dir / "scene_summary.json"
                with open(summary_path, "w", encoding="utf-8") as f:
                    json.dump(scene_summary_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Scene summary saved to {summary_path}")
        except Exception as e:
            logger.warning(f"Scene summary JSON parse failed: {e}")

    if not scene_summary_data:
        scene_summary_data = {"raw_description": description, "animal_type": "알 수 없음"}

    animal_hint = ""
    animal_type = scene_summary_data.get("animal_type", "")
    if "고양이" in animal_type or "cat" in animal_type.lower():
        animal_hint = "Hint: Use a slightly cynical, arrogant, or independent tone for cats."
    elif "강아지" in animal_type or "개" in animal_type or "dog" in animal_type.lower():
        animal_hint = "Hint: Use an enthusiastic, loyal, or slightly goofy tone for dogs."
    elif "새" in animal_type or "조류" in animal_type or "bird" in animal_type.lower():
        animal_hint = "Hint: Use a chaotic, unpredictable, or fast-paced tone for birds."

    # ── Step 2: Generate Subtitle Candidates ──
    summary_json_str = json.dumps(scene_summary_data, ensure_ascii=False, indent=2)
    
    candidates_prompt = f"""
You are an expert video subtitle creator for funny animal shorts.
Generate 3 candidate subtitle sets based ONLY on the following scene summary.
Do NOT hallucinate actions not present in the summary.
NO forced office worker (직장인) jokes unless it perfectly matches the scene.
Prioritize short, punchy, "reaction style" (짧은 대사형/반응형) over long explanations.
DO NOT use simple exclamation sentences or plain descriptions.
{animal_hint}

Scene Summary:
{summary_json_str}

Styles to generate:
1. cute_observer
2. misunderstanding_twist
3. relationship_drama

Reference these HOOKs for Line 1 (Pick or get inspired by):
{json.dumps(HOOK_LIBRARY, ensure_ascii=False)}

Reference these ENDINGs for Line 4 (Loop-friendly):
{json.dumps(ENDING_LIBRARY, ensure_ascii=False)}

Rules for EACH subtitle set (CRITICAL):
- Must consist of exactly 4 lines (Korean).
- Line 1: Short Hook (1-2 words, short reaction)
- Line 2 & 3: Action/Change reaction (Very short, conversational)
- Line 4: Short Punch/Twist (Loop-friendly ending)
- MAXIMUM 8~12 characters per line. If longer, you MUST use '\\n' to split into exactly 2 lines.
- ABSOLUTELY NO MORE THAN 2 lines per subtitle text.
- MAXIMUM 20 characters total per subtitle text.
- Make it situational, strictly based on the factual summary.

Output MUST be a JSON object with the following structure:
{{
  "candidates": {{
    "cute_observer": {{"subtitles": ["line1", "line2", "line3", "line4"], "score": 85}},
    "misunderstanding_twist": {{"subtitles": ["line1", "line2", "line3", "line4"], "score": 92}},
    "relationship_drama": {{"subtitles": ["line1", "line2", "line3", "line4"], "score": 88}}
  }},
  "best_style": "misunderstanding_twist",
  "selected_hook_type": "오해형",
  "selected_ending": "다시 봐도 어이없음"
}}
Score should be from 0 to 100 based on brevity and how well it matches the scene without hallucinating. The shortest and most punchy style should get the highest score. best_style should be the key of the highest scored candidate.
Ensure valid JSON output without any trailing characters.
"""
    raw_candidates = call_llm(candidates_prompt, settings)
    
    if raw_candidates:
        try:
            text = raw_candidates.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(text)
            
            best_style = data.get("best_style", "misunderstanding_twist")
            candidates = data.get("candidates", {})
            best_subs = candidates.get(best_style, {}).get("subtitles", [])
            
            if len(best_subs) >= 4:
                formatted_subs = []
                for s in best_subs[:4]:
                    txt = str(s).strip()
                    if '\\n' in txt:
                        txt = txt.replace('\\n', '\n')
                    elif len(txt) > 10:
                        # Auto wrap at closest space
                        words = txt.split()
                        if len(words) > 1:
                            mid = len(words) // 2
                            txt = ' '.join(words[:mid]) + '\n' + ' '.join(words[mid:])
                    
                    # Hard truncate if still too long (fallback)
                    lines = txt.split('\n')
                    if len(lines) > 2:
                        lines = lines[:2]
                        txt = '\n'.join(lines)
                    
                    formatted_subs.append(txt)

                # Save debug output with the final processed subtitles
                if debug_dir:
                    data["final_rendered"] = formatted_subs
                    candidates_path = debug_dir / "subtitle_candidates.json"
                    with open(candidates_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Subtitle candidates saved to {candidates_path}")

                return formatted_subs
            
        except Exception as e:
            logger.warning(f"Subtitle candidates JSON parse failed: {e}")

    logger.warning("LLM generation/parsing failed, using defaults")
    return _DEFAULTS
