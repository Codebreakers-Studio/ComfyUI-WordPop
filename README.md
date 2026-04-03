# ComfyUI-WordPop

**Word-by-word subtitle generator with pop & karaoke effects for ComfyUI.**

WordPop transcribes audio using Whisper AI, then renders animated word-by-word subtitles as transparent overlays you can layer onto any video. It works as both a ComfyUI custom node and a standalone CLI tool.

> **v0.1.0 Dev Beta** — Early access release for testing and feedback.

---

## Features

- **AI Transcription** — Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for accurate word-level timestamps (models: tiny, base, small, medium, large-v3)
- **Pop Mode** — Words appear one at a time with scale-up + glow animation
- **Karaoke Mode** — Full lines displayed with word-by-word color fill
- **6 Style Presets** — `neon`, `clean`, `bold`, `minimal`, `fire`, `boxed`
- **Transparent Overlay Output** — WebM (VP9+alpha) or MOV (PNG+alpha) ready to drop into any video editor
- **Burned-In Video** — Subtitles composited directly onto source video
- **ASS Subtitle Export** — Standard subtitle file compatible with all major editors
- **ComfyUI Node** — Outputs IMAGE tensors (overlay + video) for direct use with VHS_VideoCombine and other nodes
- **Resolution Scaling** — Styles auto-scale to match any resolution (16:9 and 9:16 supported)
- **Custom Text Override** — Replace Whisper's transcription with your own text while keeping the AI timing
- **CPU & CUDA** — Works on any hardware, GPU acceleration when available

## Installation

### ComfyUI Custom Node

1. Copy the `ComfyUI-WordPop` folder into your `ComfyUI/custom_nodes/` directory
2. Install dependencies:
   ```
   pip install faster-whisper rich
   ```
3. Restart ComfyUI — the **Word Pop Subtitles** node appears under `Codebreakers/Video`

### Standalone CLI (Optional)

1. Double-click `INSTALL.bat` — it checks for Python, downloads FFmpeg if needed, and installs packages
2. Double-click `Word-Pop.bat` to launch the interactive CLI

## Usage

### ComfyUI Node

The **Word Pop Subtitles** node accepts:

| Input | Type | Description |
|-------|------|-------------|
| `audio` | AUDIO | Audio signal to transcribe (optional if video provided) |
| `video_frames` | IMAGE | Video frames to burn subtitles onto (optional) |
| `model` | Selection | Whisper model size (tiny/base/small/medium/large-v3) |
| `device` | Selection | CPU or CUDA |
| `style_preset` | Selection | Visual style (neon, clean, bold, minimal, fire, boxed) |
| `mode` | Selection | use_preset / pop / karaoke |
| `aspect_ratio` | Selection | 16:9 or 9:16 |
| `custom_text_override` | STRING | Replace transcription text (leave empty for AI) |

**Outputs:**

| Output | Type | Description |
|--------|------|-------------|
| `Transparent_Overlay` | IMAGE | RGBA frames — layer over any video |
| `Video_with_Subs` | IMAGE | RGB frames with subtitles burned in |
| `Overlay_File_Path` | STRING | Path to the saved overlay file |

### CLI

```bash
python main.py input.mp4                          # defaults (neon, pop mode)
python main.py input.mp3 --style bold             # audio-only with bold preset
python main.py input.mp4 --mode karaoke --words 5 # karaoke-style word fill
python main.py input.mp4 --style fire --model small --color "#FF0000"
python main.py --list-styles                      # show available presets
```

**CLI Outputs** (saved to `./output/`):

| File | Description |
|------|-------------|
| `*_wordpop.mp4` | Playable preview (subs on black background + audio) |
| `*_wordpop_overlay.webm` | Transparent overlay for video editors |
| `*_wordpop.ass` | ASS subtitle file |
| `*_wordpop_burned.mp4` | Subtitles burned into original video (video input only) |

## Style Presets

| Preset | Font | Size | Active Color | Glow | Notes |
|--------|------|------|-------------|------|-------|
| `neon` | Arial | 72 | White | Cyan | Default — bright glow effect |
| `clean` | Arial | 64 | White | White | Subtle shadow, minimal glow |
| `bold` | Impact | 76 | Gold | Black | Heavy outline, high contrast |
| `minimal` | Arial | 52 | White | White | Small, understated |
| `fire` | Arial | 72 | Orange-Red | Orange | Warm glow, high energy |
| `boxed` | Arial | 60 | White | Black | Semi-transparent background box |

All style parameters can be overridden via CLI flags (`--font`, `--font-size`, `--color`, `--glow-color`, etc.) or saved/loaded as JSON with `--save-style` / `--load-style`.

## Requirements

- **Python** 3.10+
- **FFmpeg** (auto-downloaded by `INSTALL.bat`, or install manually)
- **faster-whisper** >= 1.0.0
- **rich** >= 13.0.0
- **NumPy** and **PyTorch** (provided by ComfyUI when used as a node)

## Connect & Support

- **YouTube:** [Codebreakers](https://www.youtube.com/@Codebreakers)
- **Patreon:** [Codebreakers on Patreon](https://www.patreon.com/cw/codebreakers)

## License

All rights reserved. This software is provided for personal use under the terms specified by the author.
