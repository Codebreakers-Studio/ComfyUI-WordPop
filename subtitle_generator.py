"""Generate ASS (Advanced SubStation Alpha) subtitles with pop/karaoke effects."""

from dataclasses import dataclass
from pathlib import Path

from transcriber import Word
from styles import (
    WordPopStyle,
    hex_to_ass_color,
    hex_to_ass_tag_color,
    opacity_to_ass_alpha,
)


@dataclass
class WordGroup:
    """A group of words displayed together."""
    words: list[Word]
    start: float  # group start time (seconds)
    end: float    # group end time (seconds)
    text: str     # combined display text


# ── Grouping logic ───────────────────────────────────────────────────────────

def group_words(words: list[Word], style: WordPopStyle) -> list[WordGroup]:
    """
    Group words into display segments based on style settings.

    Pop mode: small groups (1-5 words), split on pauses.
    Karaoke mode: longer phrases, split on longer pauses.
    """
    if not words:
        return []

    max_per_group = style.words_per_group if style.mode == "pop" else 8
    gap_threshold = style.group_gap_ms / 1000.0
    if style.mode == "karaoke":
        gap_threshold = max(gap_threshold, 0.5)

    groups: list[WordGroup] = []
    current: list[Word] = [words[0]]

    for i in range(1, len(words)):
        prev = words[i - 1]
        curr = words[i]
        gap = curr.start - prev.end

        # Split if: too many words, long pause, or punctuation ends previous word
        if (
            len(current) >= max_per_group
            or gap > gap_threshold
            or prev.text.rstrip()[-1:] in ".!?;"
        ):
            groups.append(_make_group(current, style))
            current = [curr]
        else:
            current.append(curr)

    if current:
        groups.append(_make_group(current, style))

    return groups


def _make_group(words: list[Word], style: WordPopStyle) -> WordGroup:
    """Create a WordGroup, enforcing minimum display duration."""
    start = words[0].start
    end = words[-1].end
    min_dur = style.min_display_ms / 1000.0
    if end - start < min_dur:
        end = start + min_dur
    text = " ".join(w.text for w in words)
    return WordGroup(words=words, start=start, end=end, text=text)


# ── Time formatting ──────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Format seconds to ASS timestamp H:MM:SS.cc (centiseconds)."""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


# ── ASS generation ───────────────────────────────────────────────────────────

def generate_ass(
    words: list[Word],
    style: WordPopStyle,
    resolution: tuple[int, int] = (1920, 1080),
) -> str:
    """Generate complete ASS subtitle content."""
    res_x, res_y = resolution
    groups = group_words(words, style)

    lines = []
    lines.append(_ass_header(style, res_x, res_y))
    lines.append(_ass_styles(style))
    lines.append("")
    lines.append("[Events]")
    lines.append(
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    )

    if style.mode == "pop":
        lines.extend(_pop_events(groups, style))
    else:
        lines.extend(_karaoke_events(groups, style))

    lines.append("")
    return "\n".join(lines)


def _ass_header(style: WordPopStyle, res_x: int, res_y: int) -> str:
    return (
        "[Script Info]\n"
        "Title: Word Pop Subtitles\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {res_x}\n"
        f"PlayResY: {res_y}\n"
        "YCbCr Matrix: None"
    )


def _alignment(position: str) -> int:
    """ASS alignment number from position name."""
    return {"bottom": 2, "center": 5, "top": 8}.get(position, 2)


def _ass_styles(style: WordPopStyle) -> str:
    """Generate ASS [V4+ Styles] section."""
    align = _alignment(style.position)

    primary = hex_to_ass_color(style.active_color, alpha=0)
    secondary = hex_to_ass_color(style.inactive_color, alpha=0)
    outline = hex_to_ass_color(style.glow_color, alpha=0)

    bg_alpha = opacity_to_ass_alpha(style.bg_opacity) if style.bg_box else 128
    back = hex_to_ass_color(style.bg_color, alpha=bg_alpha)

    border_style = 3 if style.bg_box else 1
    bold_flag = -1 if style.bold else 0
    italic_flag = -1 if style.italic else 0

    header = (
        "\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding"
    )

    pop_style = (
        f"Style: WordPop,{style.font_name},{style.font_size},"
        f"{primary},{secondary},{outline},{back},"
        f"{bold_flag},{italic_flag},0,0,"
        f"100,100,0,0,{border_style},{style.glow_size:.1f},{style.shadow_depth:.1f},"
        f"{align},{style.margin_h},{style.margin_h},{style.margin_v},1"
    )

    # Karaoke needs a second style for inactive words
    karaoke_style = (
        f"Style: Karaoke,{style.font_name},{style.font_size},"
        f"{primary},{secondary},{outline},{back},"
        f"{bold_flag},{italic_flag},0,0,"
        f"100,100,0,0,{border_style},{style.glow_size:.1f},{style.shadow_depth:.1f},"
        f"{align},{style.margin_h},{style.margin_h},{style.margin_v},1"
    )

    return f"{header}\n{pop_style}\n{karaoke_style}"


# ── Pop mode events ──────────────────────────────────────────────────────────

def _pop_events(groups: list[WordGroup], style: WordPopStyle) -> list[str]:
    """Generate dialogue events for pop mode (words appear with scale+glow animation)."""
    events = []
    fade = f"\\fad({style.fade_in_ms},{style.fade_out_ms})"
    blur = f"\\blur{style.glow_blur:.1f}"

    # Pop animation: scale up then settle
    pop_in = style.pop_in_ms
    pop_out = style.pop_out_ms
    scale = style.pop_scale

    pop_up = f"\\t(0,{pop_in},\\fscx{scale}\\fscy{scale}\\blur{style.glow_blur * 1.5:.1f})"
    pop_down = f"\\t({pop_in},{pop_in + pop_out},\\fscx100\\fscy100\\blur{style.glow_blur:.1f})"

    for group in groups:
        start = _fmt_time(group.start)
        end = _fmt_time(group.end)
        text = group.text

        override = f"{{{fade}{blur}{pop_up}{pop_down}}}"
        events.append(
            f"Dialogue: 0,{start},{end},WordPop,,0,0,0,,{override}{text}"
        )

    return events


# ── Karaoke mode events ─────────────────────────────────────────────────────

def _karaoke_events(groups: list[WordGroup], style: WordPopStyle) -> list[str]:
    """Generate dialogue events for karaoke mode (full line, word-by-word highlight)."""
    events = []
    inactive_color = hex_to_ass_tag_color(style.inactive_color)
    active_color = hex_to_ass_tag_color(style.active_color)
    blur = f"\\blur{style.glow_blur:.1f}"

    for group in groups:
        start = _fmt_time(group.start)
        end = _fmt_time(group.end)

        # Build karaoke text with \kf tags
        # Start all words in inactive color, karaoke fill reveals active color
        parts = []
        for w in group.words:
            # \kf duration is in centiseconds
            dur_cs = max(1, int((w.end - w.start) * 100))
            parts.append(f"{{\\kf{dur_cs}}}{w.text}")

        # Prepend inactive color override; primary color (from style) is reveal color
        text = f"{{\\1c{active_color}\\2c{inactive_color}{blur}}}" + " ".join(parts)
        events.append(
            f"Dialogue: 0,{start},{end},Karaoke,,0,0,0,,{text}"
        )

    return events


# ── Write file ───────────────────────────────────────────────────────────────

def write_ass(
    words: list[Word],
    style: WordPopStyle,
    output_path: Path,
    resolution: tuple[int, int] = (1920, 1080),
) -> Path:
    """Generate and write ASS subtitle file. Returns the output path."""
    content = generate_ass(words, style, resolution)
    output_path.write_text(content, encoding="utf-8-sig")  # BOM for max compatibility
    return output_path
