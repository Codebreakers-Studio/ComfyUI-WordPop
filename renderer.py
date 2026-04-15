"""FFmpeg-based video rendering for Word Pop subtitles."""

import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console(force_terminal=True)


# ── FFmpeg detection ─────────────────────────────────────────────────────────

def find_ffmpeg() -> str:
    """Find ffmpeg binary. Returns path or raises RuntimeError."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    # Check bundled ffmpeg (from INSTALL.bat) and common locations
    app_dir = Path(__file__).resolve().parent
    for candidate in [
        app_dir / "ffmpeg" / "ffmpeg.exe",
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(
        "FFmpeg not found. Please install FFmpeg and add it to your PATH.\n"
        "  Windows: https://www.gyan.dev/ffmpeg/builds/  (download, extract, add bin/ to PATH)\n"
        "  macOS:   brew install ffmpeg\n"
        "  Linux:   sudo apt install ffmpeg"
    )


def find_ffprobe() -> str:
    """Find ffprobe binary. Returns path or raises RuntimeError."""
    path = shutil.which("ffprobe")
    if path:
        return path
    ffmpeg = find_ffmpeg()
    ffprobe = Path(ffmpeg).parent / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    if ffprobe.exists():
        return str(ffprobe)
    raise RuntimeError("ffprobe not found. It should be installed alongside FFmpeg.")


# ── Probe helpers ────────────────────────────────────────────────────────────

def get_media_duration(input_path: Path) -> float:
    """Get duration of media file in seconds."""
    ffprobe = find_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(input_path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
    return float(result.stdout.strip())


def get_video_resolution(input_path: Path) -> tuple[int, int] | None:
    """Get video resolution, or None if file has no video stream."""
    ffprobe = find_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", str(input_path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    parts = result.stdout.strip().split("x")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    return None


def has_video_stream(input_path: Path) -> bool:
    """Check if file contains a video stream."""
    return get_video_resolution(input_path) is not None


# ── Rendering ────────────────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list[str], label: str) -> None:
    """Run an FFmpeg command with progress spinner."""
    with Progress(
        SpinnerColumn("dots2" if sys.platform != "win32" else "line"),
        TextColumn(f"[bold green]{label}"),
        TimeElapsedColumn(),
        console=Console(force_terminal=True),
    ) as progress:
        progress.add_task(label, total=None)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
        )

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        error_lines = [l for l in stderr.splitlines() if not l.startswith("  ")]
        short_err = "\n".join(error_lines[-5:]) if error_lines else stderr[-500:]
        raise RuntimeError(f"FFmpeg failed during '{label}':\n{short_err}")


def render_overlay(
    ass_path: Path,
    output_path: Path,
    duration: float,
    resolution: tuple[int, int] = (1920, 1080),
    overlay_format: str = "webm",
) -> Path:
    """
    Render subtitles on a transparent background.
    Output: WebM (VP9+alpha) or MOV (PNG codec+alpha).
    """
    ffmpeg = find_ffmpeg()
    w, h = resolution

    # Escape path for ASS filter (backslashes and colons need escaping)
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")

    if overlay_format == "mov":
        # Generate transparent RGBA overlay using PNG codec in MOV container.
        # libass does NOT write to the alpha channel — it only draws RGB.
        # So we render ASS onto black twice: once for visible RGB, once
        # converted to grayscale as an alpha matte. alphamerge combines them.
        # Black pixels (background) → alpha 0 (transparent).
        # Non-black pixels (text + glow) → alpha from luminance (opaque).
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={w}x{h}:d={duration:.3f},format=rgba",
            "-vf", f"split[rgb][alpha];[rgb]ass='{ass_escaped}'[text];[alpha]ass='{ass_escaped}',format=gray[mask];[text][mask]alphamerge",
            "-c:v", "png",
            "-pix_fmt", "rgba",
            "-t", f"{duration:.3f}",
            str(output_path),
        ]
    else:  # webm
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={w}x{h}:d={duration:.3f},format=rgba",
            "-vf", f"split[rgb][alpha];[rgb]ass='{ass_escaped}'[text];[alpha]ass='{ass_escaped}',format=gray[mask];[text][mask]alphamerge",
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-b:v", "2M",
            "-t", f"{duration:.3f}",
            str(output_path),
        ]

    _run_ffmpeg(cmd, "Rendering transparent overlay…")
    return output_path


def render_preview(
    ass_path: Path,
    audio_path: Path,
    output_path: Path,
    duration: float,
    resolution: tuple[int, int] = (1920, 1080),
) -> Path:
    """Render subtitles on black background with audio — a playable preview."""
    ffmpeg = find_ffmpeg()
    w, h = resolution
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")

    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s={w}x{h}:d={duration:.3f}",
        "-i", str(audio_path),
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]

    _run_ffmpeg(cmd, "Rendering preview video...")
    return output_path


def render_burned(
    input_path: Path,
    ass_path: Path,
    output_path: Path,
) -> Path:
    """Burn subtitles into a video file (video input only)."""
    ffmpeg = find_ffmpeg()
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ]

    _run_ffmpeg(cmd, "Burning subtitles into video…")
    return output_path
