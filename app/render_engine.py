"""
render_engine.py — Animal Shorts Auto Builder

Visual stack (bottom → top):
  1. Beat-divided video  (4 zoom/crop segments → concatenated → vignette)
  2. Subtitle cards      (rounded PIL cards per segment)
  3. Accent lines        (above bottom cards)
  4. Text overlays       (PIL keyword-highlight or TextClip)
  5. Progress bar        (dynamic, template-colored)
  6. Global fade in/out

Audio stack:
  original video audio (0.8x) + BGM (0.25x) + SFX pops + ending SFX

Template config loaded from config/templates.yaml at runtime.
"""
import logging
import random
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Keyword highlight list (Korean office/meme/pet culture)
_KEYWORDS = frozenset([
    "집사", "출근", "퇴근", "월급", "사장", "직장인", "표정", "눈빛",
    "현실", "정색", "월요일", "화요일", "수요일", "목요일", "금요일",
    "야근", "상사", "면접", "짤림", "회식", "보고서", "미팅", "반전",
    "데드라인", "커피", "카페", "밥벌이", "갑자기", "찐",
])

_DEFAULT_TEMPLATE_KEY = "info_shock_capture"


# ── Template loader ───────────────────────────────────────────────────────────

def _load_template(settings: dict) -> dict:
    """
    Load template config from config/templates.yaml and normalize
    to a flat dict the render pipeline can consume directly.
    Falls back to office_relatable defaults if yaml is missing or invalid.
    """
    tmpl_key = settings.get("project", {}).get("template_type", _DEFAULT_TEMPLATE_KEY)

    raw: dict = {}
    cfg_path = Path(__file__).parent.parent / "config" / "templates.yaml"
    if cfg_path.exists():
        try:
            import yaml
            with open(cfg_path, encoding="utf-8") as f:
                all_tpl = yaml.safe_load(f) or {}
            raw = all_tpl.get(tmpl_key) or all_tpl.get(_DEFAULT_TEMPLATE_KEY) or {}
        except Exception as e:
            logger.warning(f"templates.yaml load failed: {e}")

    colors  = raw.get("colors", {})
    layout  = raw.get("layout", {})
    lhook   = layout.get("hook", {})
    lcap    = layout.get("caption", {})
    lend    = layout.get("ending", {})
    timing  = raw.get("timing", {})
    beats   = raw.get("beats", [[1.00, 0.00], [1.06, -0.01], [1.10, 0.00], [1.06, 0.01]])
    pi      = raw.get("pattern_interrupt", {})

    def _c(v, fallback: tuple) -> tuple:
        if isinstance(v, (list, tuple)) and len(v) >= 3:
            return (int(v[0]), int(v[1]), int(v[2]))
        return fallback

    return {
        # ── Colors ──
        "hook_color":   colors.get("hook_text", "yellow"),
        "caption_color": colors.get("caption_text", "white"),
        "ending_color": colors.get("ending_text", "white"),
        "hook_bg":      _c(colors.get("hook_bg"),      (18, 18, 28)),
        "caption_bg":   _c(colors.get("caption_bg"),   (18, 18, 28)),
        "ending_bg":    _c(colors.get("ending_bg"),    (110, 42, 0)),
        "accent":       _c(colors.get("accent"),       (205, 175, 90)),
        "progress":     _c(colors.get("progress"),     (205, 175, 90)),
        "hl_color":     _c(colors.get("keyword_hl"),   (255, 210, 60)),
        # ── Layout: hook bar ──
        "hook_h":       int(lhook.get("h", 156)),
        "hook_top":     int(lhook.get("y", 48)),
        "hook_alpha":   float(lhook.get("alpha", 0.80)),
        "hook_font_sz": int(lhook.get("font_size", 66)),
        "hook_stroke":  int(lhook.get("stroke", 3)),
        "hook_radius":  int(lhook.get("radius", 0)),
        # ── Layout: caption box ──
        "cap_h":        int(lcap.get("h", 164)),
        "cap_bottom":   int(lcap.get("bottom_margin", 96)),
        "cap_inset_x":  int(lcap.get("inset_x", 108)),
        "cap_alpha":    float(lcap.get("alpha", 0.76)),
        "cap_font_sz":  int(lcap.get("font_size", 64)),
        "cap_stroke":   int(lcap.get("stroke", 3)),
        "cap_radius":   int(lcap.get("radius", 18)),
        # ── Layout: ending box ──
        "end_h":        int(lend.get("h", 188)),
        "end_alpha":    float(lend.get("alpha", 0.84)),
        "end_font_sz":  int(lend.get("font_size", 74)),
        "end_stroke":   int(lend.get("stroke", 4)),
        "end_radius":   int(lend.get("radius", 18)),
        # ── Layout: misc ──
        "accent_h":     int(layout.get("accent_h", 4)),
        "progress_h":   int(layout.get("progress_h", 8)),
        "progress_bot": int(layout.get("progress_bottom", 14)),
        # ── Beat profiles ──
        "beats": [(float(b[0]), float(b[1])) for b in beats],
        # ── Pattern interrupt ──
        "pi_enabled":    bool(pi.get("enabled", True)),
        "pi_zoom_start": float(pi.get("zoom_start", 1.09)),
        "pi_settle":     float(pi.get("settle_time", 0.42)),
        # ── Vignette ──
        "vignette":     float(raw.get("vignette_strength", 0.50)),
        # ── Timing ──
        "hook_slam":    float(timing.get("hook_slam", 0.08)),
        "cap_fade":     float(timing.get("caption_fade", 0.20)),
        "fade_in":      float(timing.get("global_fade_in", 0.30)),
        "fade_out":     float(timing.get("global_fade_out", 0.42)),
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def render_video(
    clip_paths: list[Path],
    subtitles: list[str],
    output_path: Path,
    settings: dict,
    covers_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Render a 9:16 short video with beat division, subtitles, and audio mix.
    Optional covers_dir: extract thumbnail frames and save as JPEG there.
    """
    try:
        from moviepy import (
            VideoFileClip, TextClip, ImageClip, VideoClip,
            CompositeVideoClip, concatenate_videoclips,
        )
    except ImportError:
        logger.error("moviepy not installed. Run: pip install moviepy==2.1.1")
        return None

    vid      = settings.get("video", {})
    width    = int(vid.get("width", 1080))
    height   = int(vid.get("height", 1920))
    fps      = int(vid.get("fps", 30))
    duration = float(vid.get("duration", 15))
    use_bgm  = bool(vid.get("use_bgm", False))

    tmpl  = _load_template(settings)
    fonts = _resolve_fonts(settings)

    try:
        from moviepy import VideoFileClip, concatenate_videoclips
        
        loaded_clips = []
        for p in clip_paths:
            try:
                loaded_clips.append(VideoFileClip(str(p)))
            except Exception as e:
                logger.warning(f"Failed to load {p}: {e}")
                
        if not loaded_clips:
            logger.error("No valid clips loaded.")
            return None

        segment_dur = duration / len(loaded_clips)
        processed_clips = []
        
        for c in loaded_clips:
            # 길이를 segment_dur로 맞춤
            if c.duration < segment_dur:
                import math
                n = math.ceil(segment_dur / c.duration)
                c = concatenate_videoclips([c] * n).subclipped(0, segment_dur)
            else:
                c = c.subclipped(0, segment_dur)
                
            # 중앙 크롭 9:16 및 1080x1920 리사이즈
            sw, sh = c.size
            tr = width / height
            if (sw / sh) > tr:
                c = c.cropped(x_center=sw / 2, width=int(sh * tr), height=sh)
            else:
                c = c.cropped(y_center=sh / 2, width=sw, height=int(sw / tr))
            c = c.resized((width, height))
            processed_clips.append(c)

        raw_clip = concatenate_videoclips(processed_clips)
        total_dur = duration

        # ── Cover frame extraction (before any effects) ───────────────────
        if covers_dir is not None and clip_paths:
            extract_covers(clip_paths[0], covers_dir)

        # ── Subtitle timing (컷 리듬 안정화) ──────────────────────────────────
        subs     = _pad_subtitles(subtitles, 4)
        
        hook_end = min(2.4, max(1.8, total_dur * 0.2))
        mid2_end = max(total_dur - 1.8, min(total_dur - 1.2, total_dur * 0.85))
        mid1_end = hook_end + (mid2_end - hook_end) / 2

        timing = [
            (0.0,      hook_end,  subs[0], "bottom"),
            (hook_end, mid1_end,  subs[1], "bottom"),
            (mid1_end, mid2_end,  subs[2], "bottom"),
            (mid2_end, total_dur, subs[3], "ending"),
        ]


        # ── Beat division: 4 cuts with zoom/crop ─────────────────────────────
        pi_cfg = {
            "enabled":    tmpl["pi_enabled"],
            "zoom_start": tmpl["pi_zoom_start"],
            "settle":     tmpl["pi_settle"],
        } if tmpl["pi_enabled"] else None

        beats = _make_beats(raw_clip, timing, tmpl["beats"], width, height, pi_cfg)
        clip  = concatenate_videoclips(beats)

        # ── Vignette (numpy-only, fast) ───────────────────────────────────────
        clip = _apply_vignette(clip, width, height, tmpl["vignette"])

        # ── Build overlay layers ──────────────────────────────────────────────
        layers    = [clip]
        sub_fade  = tmpl["cap_fade"]

        for t_start, t_end, text, role in timing:
            seg = t_end - t_start
            if seg < 0.2 or not text.strip():
                continue

            is_top    = role == "top_hook"
            is_ending = role == "ending"
            cap_w     = width - 2 * tmpl["cap_inset_x"]

            # Card dimensions + colors
            if is_top:
                cw, ch, cr   = width - 2 * tmpl["cap_inset_x"], tmpl["hook_h"], tmpl["hook_radius"]
                c_bg         = tmpl["hook_bg"]
                c_alpha      = tmpl["hook_alpha"]
                cx           = (width - cw) // 2
                cy           = height - tmpl["cap_bottom"] - ch
                font_sz      = tmpl["hook_font_sz"]
                txt_col      = tmpl["hook_color"]
                stroke_w     = tmpl["hook_stroke"]
                font_path    = fonts.get("top_hook")
            elif is_ending:
                cw, ch, cr   = cap_w, tmpl["end_h"], tmpl["end_radius"]
                c_bg         = tmpl["ending_bg"]
                c_alpha      = tmpl["end_alpha"]
                cx           = (width - cw) // 2
                cy           = height - tmpl["cap_bottom"] - ch
                font_sz      = tmpl["end_font_sz"]
                txt_col      = tmpl["ending_color"]
                stroke_w     = tmpl["end_stroke"]
                font_path    = fonts.get("ending")
            else:
                cw, ch, cr   = cap_w, tmpl["cap_h"], tmpl["cap_radius"]
                c_bg         = tmpl["caption_bg"]
                c_alpha      = tmpl["cap_alpha"]
                cx           = (width - cw) // 2
                cy           = height - tmpl["cap_bottom"] - ch
                font_sz      = tmpl["cap_font_sz"]
                txt_col      = tmpl["caption_color"]
                stroke_w     = tmpl["cap_stroke"]
                font_path    = fonts.get("body")

            # ── Rounded card ─────────────────────────────────────────────
            try:
                from moviepy.video.fx import FadeIn as _FI
                card = (
                    ImageClip(_make_card(cw, ch, c_bg, c_alpha, cr))
                    .with_duration(seg).with_start(t_start)
                    .with_position((cx, cy))
                    .with_effects([_FI(sub_fade)])
                )
                layers.append(card)
            except Exception as e:
                logger.warning(f"Card [{role}]: {e}")

            # ── Accent line above bottom/ending cards ─────────────────────
            if not is_top:
                try:
                    acc = (
                        ImageClip(_make_card(cw, tmpl["accent_h"], tmpl["accent"], 1.0, 0))
                        .with_duration(seg).with_start(t_start)
                        .with_position((cx, cy - tmpl["accent_h"]))
                    )
                    layers.append(acc)
                except Exception as e:
                    logger.warning(f"Accent [{role}]: {e}")

            # ── Text: PIL keyword-highlight first, fallback TextClip ──────
            text_y = cy + max(8, (ch - font_sz) // 2)
            txt_added = False

            if font_path:
                hl_arr = _make_highlighted_text(
                    text, font_path, font_sz,
                    _color_str_to_rgb(txt_col),
                    tmpl["hl_color"],
                    stroke_w,
                )
                if hl_arr is not None:
                    try:
                        from moviepy.video.fx import FadeIn as _FI3
                        hl_clip = (
                            ImageClip(hl_arr)
                            .with_duration(seg).with_start(t_start)
                            .with_position(("center", text_y))
                            .with_effects([_FI3(sub_fade)])
                        )
                        layers.append(hl_clip)
                        txt_added = True
                    except Exception as e:
                        logger.warning(f"HL ImageClip [{role}]: {e}")

            if not txt_added:
                txt_kw: dict = {
                    "text": text, "font_size": font_sz,
                    "color": txt_col,
                    "stroke_color": "black", "stroke_width": stroke_w,
                }
                if font_path:
                    txt_kw["font"] = font_path
                try:
                    from moviepy.video.fx import FadeIn as _FI4
                    tc = (
                        TextClip(**txt_kw)
                        .with_duration(seg).with_start(t_start)
                        .with_position(("center", text_y))
                        .with_effects([_FI4(sub_fade)])
                    )
                    layers.append(tc)
                except Exception as e:
                    logger.warning(f"TextClip [{role}]: {e}")

            # ── Ending emphasis: bright bottom line in last 0.8s ──────────
            if is_ending and seg > 1.5:
                emph_start = t_end - 0.8
                try:
                    em = (
                        ImageClip(_make_card(cw, tmpl["accent_h"] + 2, tmpl["accent"], 1.0, 0))
                        .with_duration(0.8).with_start(emph_start)
                        .with_position((cx, cy + ch))
                    )
                    layers.append(em)
                except Exception as e:
                    logger.warning(f"Ending emphasis: {e}")

        # ── Progress bar ──────────────────────────────────────────────────────
        try:
            prog = _make_progress_bar(
                width, total_dur, tmpl["progress"], tmpl["progress_h"]
            )
            layers.append(prog.with_position((0, height - tmpl["progress_h"] - tmpl["progress_bot"])))
        except Exception as e:
            logger.warning(f"Progress bar: {e}")

        # ── Composite + global fade ───────────────────────────────────────────
        composite = CompositeVideoClip(layers, size=(width, height))
        try:
            from moviepy.video.fx import FadeIn, FadeOut
            composite = composite.with_effects([
                FadeIn(tmpl["fade_in"]), FadeOut(tmpl["fade_out"])
            ])
        except Exception as e:
            logger.warning(f"Global fade: {e}")

        # ── Audio mix: original + BGM + SFX ──────────────────────────────────
        composite = _mix_audio(composite, timing, use_bgm, total_dur, mid2_end)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        composite.write_videofile(
            str(output_path), fps=fps,
            codec="libx264", audio_codec="aac", logger=None,
        )
        logger.info(f"Rendered: {output_path}")
        return output_path

    except Exception as e:
        if "ffmpeg" in str(e).lower():
            logger.exception(f"[렌더 실패 - FFmpeg] {e}\n→ pip install imageio-ffmpeg")
        else:
            logger.exception(f"[렌더 실패] {e}")
        return None


# ── Cover frame extraction ─────────────────────────────────────────────────────

def extract_covers(
    clip_path: Path,
    output_dir: Path,
    timestamps: tuple = (0.8, 1.2, 2.0),
) -> list[Path]:
    """
    Extract JPEG thumbnail frames from a video at given timestamps.
    Saves to output_dir/covers/cover_{ts}s.jpg.
    Returns list of saved paths (skips timestamps beyond clip duration).
    """
    saved: list[Path] = []
    try:
        from moviepy import VideoFileClip
        from PIL import Image

        covers_path = output_dir / "covers"
        covers_path.mkdir(parents=True, exist_ok=True)

        clip = VideoFileClip(str(clip_path))
        for ts in timestamps:
            if ts >= clip.duration:
                continue
            frame = clip.get_frame(ts)          # numpy uint8 HxWx3
            img   = Image.fromarray(frame)
            out   = covers_path / f"cover_{ts:.1f}s.jpg"
            img.save(str(out), "JPEG", quality=90)
            saved.append(out)
            logger.info(f"Cover saved: {out}")
        clip.close()
    except Exception as e:
        logger.warning(f"Cover extraction failed: {e}")
    return saved


# ── Beat division ─────────────────────────────────────────────────────────────

def _make_beats(
    clip,
    timing: list,
    beat_profiles: list[tuple],
    width: int,
    height: int,
    pattern_interrupt: Optional[dict] = None,
    loop_frame = None,
) -> list:
    """
    Split clip into N beats aligned to subtitle timing.
    Each beat gets a different static zoom/crop profile.
    Beat 0 (top_hook) gets animated pattern interrupt if enabled.
    """
    beats = []
    for i, (t_start, t_end, _, _role) in enumerate(timing):
        if t_end <= t_start:
            continue
        zoom, y_off = beat_profiles[min(i, len(beat_profiles) - 1)]
        beat = clip.subclipped(t_start, t_end)
        sw, sh = beat.size

        # Apply pattern interrupt only on beat 0
        if i == 0 and pattern_interrupt and pattern_interrupt.get("enabled"):
            beat = _apply_pattern_interrupt(
                beat, sw, sh, width, height,
                pattern_interrupt["zoom_start"],
                zoom,
                pattern_interrupt["settle"],
            )
        else:
            nw = max(1, int(sw / zoom))
            nh = max(1, int(sh / zoom))
            cx = sw // 2
            cy = min(max(nh // 2, int(sh // 2 + sh * y_off)), sh - nh // 2)
            try:
                beat = beat.cropped(x_center=cx, y_center=cy, width=nw, height=nh)
                beat = beat.resized((width, height))
                
                # 프리즈 프레임: 마지막 펀치라인 강조 및 루프 유도
                if i == 3 and pattern_interrupt and pattern_interrupt.get("enabled"):
                    try:
                        from moviepy import ImageClip, concatenate_videoclips
                        
                        hold_duration = 0.6
                        move_duration = beat.duration - hold_duration
                        
                        if move_duration > 0.1:
                            move_clip = beat.subclipped(0, move_duration)
                            freeze_frame = beat.get_frame(move_duration)
                            freeze_clip = ImageClip(freeze_frame).with_duration(hold_duration)
                            beat = concatenate_videoclips([move_clip, freeze_clip])
                        else:
                            freeze_frame = beat.get_frame(min(0.2, beat.duration * 0.5))
                            beat = ImageClip(freeze_frame).with_duration(beat.duration)
                            
                    except Exception as fe:
                        logger.warning(f"Freeze frame failed: {fe}")
                        
            except Exception as e:
                logger.warning(f"Beat {i} crop/resize failed: {e}")

        beats.append(beat)
    return beats if beats else [clip]


def _apply_pattern_interrupt(
    beat_clip,
    sw: int, sh: int,
    width: int, height: int,
    zoom_start: float,
    zoom_end: float,
    settle_time: float,
):
    """
    Animate zoom from zoom_start → zoom_end over settle_time seconds (per-frame).
    After settle_time, zoom stays at zoom_end (static crop).
    """
    try:
        from PIL import Image as _PILImage

        def _tx(get_frame, t):
            frame = get_frame(t)
            fh, fw = frame.shape[:2]
            # Linear interpolation: start → end over settle_time
            if t >= settle_time:
                z = zoom_end
            else:
                progress = t / max(settle_time, 1e-6)
                z = zoom_start + (zoom_end - zoom_start) * progress

            # Crop to 1/z of the frame from center, then upscale
            if abs(z - 1.0) < 0.005:
                cropped = frame
            else:
                nw = max(1, int(fw / z))
                nh = max(1, int(fh / z))
                x1 = (fw - nw) // 2
                y1 = (fh - nh) // 2
                cropped = frame[y1:y1 + nh, x1:x1 + nw]

            if cropped.shape[1] != width or cropped.shape[0] != height:
                import numpy as np
                return np.array(
                    _PILImage.fromarray(cropped).resize((width, height), _PILImage.LANCZOS)
                )
            return cropped

        return beat_clip.transform(_tx)

    except Exception as e:
        logger.warning(f"Pattern interrupt failed, using static zoom: {e}")
        # Fallback: static crop at zoom_end
        nw = max(1, int(sw / zoom_end))
        nh = max(1, int(sh / zoom_end))
        try:
            beat_clip = beat_clip.cropped(x_center=sw // 2, y_center=sh // 2, width=nw, height=nh)
            beat_clip = beat_clip.resized((width, height))
        except Exception:
            pass
        return beat_clip


# ── Vignette ──────────────────────────────────────────────────────────────────

def _apply_vignette(clip, width: int, height: int, strength: float = 0.50):
    """Darken edges via pre-computed numpy brightness map (fast, no PIL per frame)."""
    try:
        x  = np.linspace(-1.0, 1.0, width,  dtype=np.float32)
        y  = np.linspace(-1.0, 1.0, height, dtype=np.float32)
        xx, yy = np.meshgrid(x, y)
        dist   = np.sqrt((xx * 0.58) ** 2 + (yy * 0.88) ** 2).clip(0, 1)
        bright = (1.0 - np.clip(dist ** 2.4 * strength, 0, 0.85))[:, :, np.newaxis]

        def _tx(get_frame, t):
            return np.clip(get_frame(t).astype(np.float32) * bright, 0, 255).astype(np.uint8)

        return clip.transform(_tx)
    except Exception as e:
        logger.warning(f"Vignette skipped: {e}")
        return clip


# ── PIL helpers ───────────────────────────────────────────────────────────────

def _make_card(w: int, h: int, color: tuple, alpha: float, radius: int) -> np.ndarray:
    """RGBA rounded rectangle → numpy array."""
    try:
        from PIL import Image, ImageDraw
        img  = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        fill = (int(color[0]), int(color[1]), int(color[2]), int(alpha * 255))
        draw = ImageDraw.Draw(img)
        if radius > 0:
            draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill)
        else:
            draw.rectangle([0, 0, w - 1, h - 1], fill=fill)
        return np.array(img)
    except Exception:
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        arr[:, :, :3] = [int(color[0]), int(color[1]), int(color[2])]
        arr[:, :, 3]  = int(alpha * 255)
        return arr


def _make_highlighted_text(
    text: str,
    font_path: str,
    font_size: int,
    base_rgb: tuple,
    hl_rgb: tuple,
    stroke_w: int,
) -> Optional[np.ndarray]:
    """
    Render text with keyword highlighting via PIL.
    Returns RGBA array or None (→ caller falls back to TextClip).
    """
    found_kw = next((kw for kw in _KEYWORDS if kw in text), None)
    if not found_kw:
        return None

    try:
        from PIL import Image, ImageDraw, ImageFont

        font = ImageFont.truetype(font_path, font_size)
        dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

        fb = dummy_draw.textbbox((0, 0), text, font=font)
        tw = fb[2] - fb[0]
        th = fb[3] - fb[1]
        pad = stroke_w + 4

        kw_idx   = text.find(found_kw)
        before   = text[:kw_idx]
        bb_b     = dummy_draw.textbbox((0, 0), before, font=font) if before else (0, 0, 0, 0)
        before_w = bb_b[2] - bb_b[0] if before else 0

        cw = tw + pad * 2
        ch = th + pad * 2
        img  = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        ox = pad - fb[0]
        oy = pad - fb[1]

        # Stroke (black outline)
        for dx in range(-stroke_w, stroke_w + 1):
            for dy in range(-stroke_w, stroke_w + 1):
                if abs(dx) + abs(dy) <= stroke_w + 1:
                    draw.text((ox + dx, oy + dy), text, font=font, fill=(0, 0, 0, 255))

        draw.text((ox, oy), text, font=font, fill=(*base_rgb, 255))
        draw.text((ox + before_w, oy), found_kw, font=font, fill=(*hl_rgb, 255))

        return np.array(img)

    except Exception as e:
        logger.warning(f"PIL highlight failed: {e}")
        return None


def _color_str_to_rgb(color: str) -> tuple:
    mapping = {
        "white":  (255, 255, 255),
        "yellow": (255, 230, 0),
        "black":  (0, 0, 0),
        "orange": (255, 140, 0),
    }
    return mapping.get(color.lower(), (255, 255, 255))


# ── Progress bar ──────────────────────────────────────────────────────────────

def _make_progress_bar(width: int, total_dur: float, color: tuple, bar_h: int = 8):
    from moviepy import VideoClip
    c = np.array(color, dtype=np.uint8)

    def _f(t):
        bw = int(width * min(t / max(total_dur, 0.001), 1.0))
        f  = np.zeros((bar_h, width, 3), dtype=np.uint8)
        if bw > 0:
            f[:, :bw] = c
        return f

    return VideoClip(_f, duration=total_dur)


# ── Font resolution ───────────────────────────────────────────────────────────

def _resolve_fonts(settings: dict) -> dict[str, Optional[str]]:
    """Return {role: font_path} for top_hook, body, ending."""
    typo     = settings.get("typography", {})
    font_dir = Path(__file__).parent.parent / "assets" / "fonts"
    win_fallbacks = [
        Path("C:/Windows/Fonts/malgunbd.ttf"),
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]

    def _resolve(key: str) -> Optional[str]:
        spec = typo.get(key, "").strip()
        if spec:
            p = Path(spec)
            if p.is_absolute() and p.exists():
                return str(p)
            c = font_dir / spec
            if c.exists():
                return str(c)
        if font_dir.exists():
            for pat in ("*ExtraBold*", "*Bold*", "*Black*", "*.ttf", "*.otf"):
                hits = list(font_dir.glob(pat))
                if hits:
                    return str(hits[0])
        for p in win_fallbacks:
            if p.exists():
                return str(p)
        return None

    return {
        "top_hook": _resolve("top_hook_font"),
        "body":     _resolve("body_font"),
        "ending":   _resolve("ending_font"),
    }


# ── Audio ─────────────────────────────────────────────────────────────────────

def _mix_audio(composite, timing, use_bgm: bool, total_dur: float, mid2_end: float):
    """Mix original video audio + BGM (low volume) + SFX pops + ending SFX."""
    try:
        audio_tracks = []

        if composite.audio:
            try:
                from moviepy.audio.fx import MultiplyVolume
                audio_tracks.append(composite.audio.with_effects([MultiplyVolume(0.8)]))
            except Exception:
                audio_tracks.append(composite.audio)

        bgm = _load_bgm(use_bgm, total_dur)
        if bgm:
            try:
                from moviepy.audio.fx import MultiplyVolume
                bgm = bgm.with_effects([MultiplyVolume(0.25)])
            except Exception:
                pass
            audio_tracks.append(bgm)

        pop = _load_sfx("pop")
        if pop:
            # 효과음은 1~2개만 (첫 등장과 엔딩)
            for i, (t_start, _, _, role) in enumerate(timing):
                if role in ("bottom", "ending") and t_start > 0 and i in (1, 3):
                    try:
                        audio_tracks.append(pop.with_start(t_start))
                    except Exception:
                        pass

        ending_sfx = _load_sfx("ending")
        if ending_sfx:
            try:
                audio_tracks.append(ending_sfx.with_start(mid2_end))
            except Exception:
                pass

        if len(audio_tracks) > 1:
            from moviepy import CompositeAudioClip
            return composite.with_audio(CompositeAudioClip(audio_tracks))
        elif len(audio_tracks) == 1 and not composite.audio:
            return composite.with_audio(audio_tracks[0])

    except Exception as e:
        logger.warning(f"Audio mix failed: {e}")

    return composite


def _load_bgm(use_bgm: bool, duration: float) -> Optional[object]:
    if not use_bgm:
        return None
    try:
        from moviepy import AudioFileClip
        d = Path(__file__).parent.parent / "assets" / "music"
        if not d.exists():
            return None
        tracks = list(d.glob("*.mp3")) + list(d.glob("*.wav"))
        if not tracks:
            return None
        a = AudioFileClip(str(random.choice(tracks)))
        return a.subclipped(0, duration) if a.duration > duration else a
    except Exception as e:
        logger.warning(f"BGM failed: {e}")
        return None


def _load_sfx(name: str) -> Optional[object]:
    try:
        from moviepy import AudioFileClip
        d = Path(__file__).parent.parent / "assets" / "sfx"
        for ext in (".wav", ".mp3"):
            p = d / (name + ext)
            if p.exists():
                return AudioFileClip(str(p))
    except Exception as e:
        logger.warning(f"SFX '{name}': {e}")
    return None


# ── Utilities ─────────────────────────────────────────────────────────────────

def _pad_subtitles(subtitles: list[str], n: int) -> list[str]:
    defaults = ["이거 실화임?", "출근 싫은 표정 그 자체", "이 눈빛 나잖아", "근데 왜 귀여움 ㅋㅋ"]
    r = list(subtitles)
    while len(r) < n:
        r.append(defaults[len(r) % len(defaults)])
    return r[:n]
