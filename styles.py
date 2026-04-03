"""Style presets and configuration for Word Pop subtitles."""

from dataclasses import dataclass, field, asdict
import json
from pathlib import Path


@dataclass
class WordPopStyle:
    """Complete style configuration for subtitle rendering."""

    # Font
    font_name: str = "Arial"
    font_size: int = 68
    bold: bool = True
    italic: bool = False

    # Colors (hex #RRGGBB)
    active_color: str = "#FFFFFF"
    inactive_color: str = "#888888"
    glow_color: str = "#00DDFF"

    # Glow / outline
    glow_size: float = 3.0
    glow_blur: float = 2.5

    # Background box
    bg_box: bool = False
    bg_color: str = "#000000"
    bg_opacity: float = 0.6

    # Shadow
    shadow_depth: float = 0.0

    # Pop animation
    pop_scale: int = 118  # percentage, 100 = no scale
    pop_in_ms: int = 80   # time to reach peak scale
    pop_out_ms: int = 120  # time to settle back

    # Fade
    fade_in_ms: int = 40
    fade_out_ms: int = 120

    # Layout
    position: str = "bottom"  # top, center, bottom
    margin_v: int = 55
    margin_h: int = 40

    # Grouping
    mode: str = "pop"           # pop or karaoke
    words_per_group: int = 1    # pop mode: words shown together (1-5)
    group_gap_ms: int = 150     # auto-group if gap < this (ms)
    min_display_ms: int = 300   # minimum time a word/group stays visible

    def save(self, path: Path):
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "WordPopStyle":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Color helpers ────────────────────────────────────────────────────────────

def hex_to_ass_color(hex_color: str, alpha: int = 0) -> str:
    """Convert #RRGGBB to ASS &HAABBGGRR format."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def hex_to_ass_tag_color(hex_color: str) -> str:
    """Convert #RRGGBB to ASS tag color &HBBGGRR& (no alpha)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H{b:02X}{g:02X}{r:02X}&"


def opacity_to_ass_alpha(opacity: float) -> int:
    """Convert 0.0-1.0 opacity to ASS alpha (0=opaque, 255=transparent)."""
    return max(0, min(255, int((1.0 - opacity) * 255)))


# ── Presets ──────────────────────────────────────────────────────────────────

PRESETS = {
    "neon": WordPopStyle(
        font_name="Arial",
        font_size=72,
        bold=True,
        active_color="#FFFFFF",
        inactive_color="#666688",
        glow_color="#00DDFF",
        glow_size=4.0,
        glow_blur=3.0,
        pop_scale=120,
        bg_box=False,
    ),
    "clean": WordPopStyle(
        font_name="Arial",
        font_size=64,
        bold=True,
        active_color="#FFFFFF",
        inactive_color="#AAAAAA",
        glow_color="#FFFFFF",
        glow_size=2.0,
        glow_blur=1.5,
        pop_scale=112,
        shadow_depth=1.5,
        bg_box=False,
    ),
    "bold": WordPopStyle(
        font_name="Impact",
        font_size=76,
        bold=True,
        active_color="#FFD700",
        inactive_color="#AA8800",
        glow_color="#000000",
        glow_size=4.0,
        glow_blur=0.5,
        pop_scale=115,
        bg_box=False,
    ),
    "minimal": WordPopStyle(
        font_name="Arial",
        font_size=52,
        bold=False,
        active_color="#FFFFFF",
        inactive_color="#999999",
        glow_color="#FFFFFF",
        glow_size=1.0,
        glow_blur=1.0,
        pop_scale=105,
        bg_box=False,
    ),
    "fire": WordPopStyle(
        font_name="Arial",
        font_size=72,
        bold=True,
        active_color="#FF4400",
        inactive_color="#882200",
        glow_color="#FFAA00",
        glow_size=4.0,
        glow_blur=3.5,
        pop_scale=122,
        bg_box=False,
    ),
    "boxed": WordPopStyle(
        font_name="Arial",
        font_size=60,
        bold=True,
        active_color="#FFFFFF",
        inactive_color="#CCCCCC",
        glow_color="#000000",
        glow_size=1.5,
        glow_blur=0.5,
        pop_scale=110,
        bg_box=True,
        bg_color="#000000",
        bg_opacity=0.65,
    ),
}


def get_preset(name: str) -> WordPopStyle:
    """Get a named preset, or raise ValueError with available names."""
    if name in PRESETS:
        return PRESETS[name]
    available = ", ".join(PRESETS.keys())
    raise ValueError(f"Unknown preset '{name}'. Available: {available}")


def list_presets() -> list[str]:
    return list(PRESETS.keys())
