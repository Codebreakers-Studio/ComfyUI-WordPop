#!/usr/bin/env python3
"""
Word Pop — Premium word-by-word subtitle generator with pop effects.

Usage:
    python main.py input.mp4                        # defaults (neon preset, pop mode)
    python main.py input.mp3 --style bold           # audio with bold preset
    python main.py input.mp4 --mode karaoke         # karaoke-style word fill
    python main.py input.mp4 --style clean --model small --color "#FF0000"
    python main.py --list-styles                    # show available presets

Outputs:
    <name>_wordpop.ass          — Subtitle file (always)
    <name>_wordpop_overlay.webm — Transparent overlay for editors (always)
    <name>_wordpop.mp4          — Video with burned-in subs (video input only)
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from styles import WordPopStyle, get_preset, list_presets, PRESETS
from transcriber import transcribe
from subtitle_generator import write_ass
from renderer import (
    find_ffmpeg,
    has_video_stream,
    get_video_resolution,
    get_media_duration,
    render_overlay,
    render_preview,
    render_burned,
)

console = Console()


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="word-pop",
        description="Word Pop — word-by-word subtitle generator with pop effects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py video.mp4\n"
            "  python main.py audio.wav --style fire --model small\n"
            "  python main.py video.mp4 --mode karaoke --words 5\n"
            "  python main.py --list-styles\n"
        ),
    )

    p.add_argument("input", nargs="?", help="Input audio or video file")
    p.add_argument("-o", "--output", help="Output directory (default: same as input)")

    # Style
    style = p.add_argument_group("style")
    style.add_argument("--style", default="neon", help="Style preset (default: neon)")
    style.add_argument("--font", help="Font name override")
    style.add_argument("--font-size", type=int, help="Font size override")
    style.add_argument("--color", help="Active word color (#RRGGBB)")
    style.add_argument("--glow-color", help="Glow color (#RRGGBB)")
    style.add_argument("--glow-size", type=float, help="Glow border size")
    style.add_argument("--bg-box", action="store_true", help="Enable background box")
    style.add_argument("--position", choices=["top", "center", "bottom"], help="Subtitle position")

    # Mode
    mode = p.add_argument_group("mode")
    mode.add_argument("--mode", choices=["pop", "karaoke"], help="Display mode (default: pop)")
    mode.add_argument("--words", type=int, help="Words per group in pop mode (default: 1)")

    # Transcription
    trans = p.add_argument_group("transcription")
    trans.add_argument("--model", default="base", help="Whisper model: tiny, base, small, medium, large-v3")
    trans.add_argument("--language", help="Language code (e.g. en). Auto-detect if omitted")
    trans.add_argument("--device", default="cpu", choices=["cpu", "cuda"], help="Device (default: cpu)")

    # Output format
    fmt = p.add_argument_group("output format")
    fmt.add_argument("--overlay-format", default="webm", choices=["webm", "mov"],
                     help="Transparent overlay format (default: webm)")
    fmt.add_argument("--resolution", help="Video resolution WxH (default: 1920x1080 or input size)")
    fmt.add_argument("-y", "--overwrite", action="store_true", help="Overwrite existing files")

    # Info
    p.add_argument("--list-styles", action="store_true", help="Show available style presets")
    p.add_argument("--save-style", help="Save current style to JSON file")
    p.add_argument("--load-style", help="Load style from JSON file")

    return p


def show_styles():
    """Display available style presets in a nice table."""
    table = Table(title="Word Pop Style Presets", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Font")
    table.add_column("Size", justify="right")
    table.add_column("Active Color")
    table.add_column("Glow Color")
    table.add_column("Mode")
    table.add_column("BG Box")

    for name, s in PRESETS.items():
        table.add_row(
            name,
            s.font_name,
            str(s.font_size),
            s.active_color,
            s.glow_color,
            s.mode,
            "yes" if s.bg_box else "no",
        )

    console.print(table)


def apply_overrides(style: WordPopStyle, args: argparse.Namespace) -> WordPopStyle:
    """Apply CLI overrides to the base style."""
    if args.font:
        style.font_name = args.font
    if args.font_size:
        style.font_size = args.font_size
    if args.color:
        style.active_color = args.color
    if args.glow_color:
        style.glow_color = args.glow_color
    if args.glow_size is not None:
        style.glow_size = args.glow_size
    if args.bg_box:
        style.bg_box = True
    if args.position:
        style.position = args.position
    if args.mode:
        style.mode = args.mode
    if args.words:
        style.words_per_group = args.words
    return style


def parse_resolution(res_str: str | None) -> tuple[int, int] | None:
    if not res_str:
        return None
    parts = res_str.lower().split("x")
    if len(parts) != 2:
        console.print(f"[red]Invalid resolution '{res_str}'. Use WxH format (e.g. 1920x1080)[/red]")
        sys.exit(1)
    return int(parts[0]), int(parts[1])


# ── Main pipeline ────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── List styles mode ─────────────────────────────────────────────────
    if args.list_styles:
        show_styles()
        return

    # ── Validate input ───────────────────────────────────────────────────
    if not args.input:
        parser.print_help()
        console.print("\n[red]Error: input file required[/red]")
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]File not found: {input_path}[/red]")
        sys.exit(1)

    # ── Check FFmpeg early ───────────────────────────────────────────────
    try:
        ffmpeg_path = find_ffmpeg()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    # ── Build style ──────────────────────────────────────────────────────
    if args.load_style:
        style = WordPopStyle.load(Path(args.load_style))
    else:
        try:
            style = get_preset(args.style)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)

    style = apply_overrides(style, args)

    if args.save_style:
        style.save(Path(args.save_style))
        console.print(f"[green]Style saved to {args.save_style}[/green]")
        return

    # ── Detect input type ────────────────────────────────────────────────
    is_video = has_video_stream(input_path)
    input_res = get_video_resolution(input_path) if is_video else None
    user_res = parse_resolution(args.resolution)
    resolution = user_res or input_res or (1920, 1080)

    # ── Output paths ─────────────────────────────────────────────────────
    script_dir = Path(__file__).resolve().parent
    out_dir = Path(args.output) if args.output else script_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    ass_path = out_dir / f"{stem}_wordpop.ass"
    overlay_ext = args.overlay_format
    overlay_path = out_dir / f"{stem}_wordpop_overlay.{overlay_ext}"
    preview_path = out_dir / f"{stem}_wordpop.mp4"  # always: playable preview
    burned_path = out_dir / f"{stem}_wordpop_burned.mp4" if is_video else None

    # Check for existing files
    if not args.overwrite:
        for p in [ass_path, overlay_path, preview_path, burned_path]:
            if p and p.exists():
                console.print(f"[red]Output file exists: {p}[/red]")
                console.print("[dim]Use -y to overwrite[/dim]")
                sys.exit(1)

    # ── Banner ───────────────────────────────────────────────────────────
    banner = Text("WORD POP", style="bold white on blue")
    info_lines = [
        f"Input:       {input_path.name}  ({'video' if is_video else 'audio'})",
        f"Resolution:  {resolution[0]}x{resolution[1]}",
        f"Style:       {args.style}  ({style.mode} mode)",
        f"Model:       {args.model}  ({args.device})",
        f"Output dir:  {out_dir}",
    ]
    console.print(Panel("\n".join(info_lines), title=banner, border_style="blue"))

    # ── Step 1: Transcribe ───────────────────────────────────────────────
    console.print("\n[bold]Step 1/3:[/bold] Transcribing audio…")
    try:
        result = transcribe(
            audio_path=input_path,
            model_name=args.model,
            language=args.language,
            device=args.device,
            compute_type="int8" if args.device == "cpu" else "float16",
        )
    except Exception as e:
        console.print(f"\n[red]Transcription failed: {e}[/red]")
        sys.exit(1)

    console.print(
        f"  [green]Done![/green] {len(result.words)} words, "
        f"language: {result.language}, duration: {result.duration:.1f}s"
    )

    # ── Step 2: Generate subtitles ───────────────────────────────────────
    console.print("\n[bold]Step 2/3:[/bold] Generating subtitles…")
    try:
        write_ass(result.words, style, ass_path, resolution)
    except Exception as e:
        console.print(f"\n[red]Subtitle generation failed: {e}[/red]")
        sys.exit(1)
    console.print(f"  [green]Saved:[/green] {ass_path}")

    # ── Step 3: Render videos ────────────────────────────────────────────
    console.print("\n[bold]Step 3/3:[/bold] Rendering video…")

    # Always render a playable preview (subs on black bg + audio)
    try:
        render_preview(
            ass_path=ass_path,
            audio_path=input_path,
            output_path=preview_path,
            duration=result.duration,
            resolution=resolution,
        )
        console.print(f"  [green]Preview:[/green] {preview_path}")
    except Exception as e:
        console.print(f"\n[red]Preview render failed: {e}[/red]")
        console.print("[dim]The .ass file was still saved — use it in your editor.[/dim]")

    # Transparent overlay for editors
    try:
        render_overlay(
            ass_path=ass_path,
            output_path=overlay_path,
            duration=result.duration,
            resolution=resolution,
            overlay_format=args.overlay_format,
        )
        console.print(f"  [green]Overlay:[/green] {overlay_path}")
    except Exception as e:
        console.print(f"\n[red]Overlay render failed: {e}[/red]")
        console.print("[dim]The .ass file was still saved — use it in your editor.[/dim]")

    # Burn into original video if input is video
    if is_video and burned_path:
        try:
            render_burned(input_path, ass_path, burned_path)
            console.print(f"  [green]Burned:[/green]  {burned_path}")
        except Exception as e:
            console.print(f"\n[red]Burned render failed: {e}[/red]")
            console.print("[dim]The .ass file was still saved — use it in your editor.[/dim]")

    # ── Summary ──────────────────────────────────────────────────────────
    console.print()
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("Subtitles", str(ass_path))
    summary.add_row("Preview", str(preview_path) + "  (playable)")
    summary.add_row("Overlay", str(overlay_path) + "  (transparent, for editors)")
    if burned_path and burned_path.exists():
        summary.add_row("Burned", str(burned_path) + "  (subs on original video)")
    console.print(Panel(summary, title="[bold green]Complete!", border_style="green"))


if __name__ == "__main__":
    main()
