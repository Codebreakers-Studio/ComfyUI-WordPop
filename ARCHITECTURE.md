# Architecture

Technical overview of the ComfyUI-WordPop codebase.

## Module Map

```
ComfyUI-WordPop/
├── __init__.py              ComfyUI entry point — registers the node
├── wordpop_node.py          ComfyUI node class (WordPop)
├── main.py                  Standalone CLI entry point
├── transcriber.py           Audio → word-level timestamps (faster-whisper)
├── subtitle_generator.py    Words → ASS subtitle file with animations
├── styles.py                Style presets and color conversion utilities
├── renderer.py              FFmpeg wrappers for video rendering
├── web/
│   └── wordpop_ui.js        ComfyUI frontend extension (minimal)
├── INSTALL.bat              One-click setup for standalone use
├── Word-Pop.bat             Interactive CLI launcher
└── requirements.txt         Python dependencies
```

## Pipeline

Both the ComfyUI node and CLI follow the same three-stage pipeline:

```
Audio/Video Input
       │
       ▼
┌──────────────┐
│  Transcribe  │  transcriber.py — faster-whisper with word_timestamps=True
│              │  Returns: list[Word] with (text, start, end, probability)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Generate ASS │  subtitle_generator.py — builds Advanced SubStation Alpha file
│              │  Pop mode:     \fad + \t scale/blur animation per word group
│              │  Karaoke mode: \kf tags for progressive word fill
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Render     │  renderer.py — FFmpeg subprocess calls
│              │  Overlay:  transparent VP9/WebM or PNG/MOV
│              │  Preview:  subs on black + audio (MP4)
│              │  Burned:   subs composited onto source video (MP4)
└──────────────┘
```

## Key Design Decisions

### Word Grouping (subtitle_generator.py)

Words are grouped before rendering:
- **Pop mode**: Groups of N words (default 1), split on pauses > `group_gap_ms` or sentence-ending punctuation
- **Karaoke mode**: Longer phrases (up to 8 words), split on longer pauses (> 500ms)
- Minimum display duration enforced (`min_display_ms`) so words don't flash too fast

### ASS Animation Tags

Pop mode uses layered ASS override tags:
- `\fad(in, out)` — fade in/out
- `\t(0, pop_in, \fscx{scale}\fscy{scale})` — scale up to peak
- `\t(pop_in, pop_in+pop_out, \fscx100\fscy100)` — settle back to normal
- `\blur` — glow effect via Gaussian blur on outline

Karaoke mode uses `\kf` (fill) tags with centisecond durations per word.

### ComfyUI Integration (wordpop_node.py)

- **Rich suppression**: Rich's live progress display deadlocks inside ComfyUI's execution model. The node monkey-patches `rich.progress.Progress` with a silent subclass before importing pipeline modules.
- **Temp-file decoding**: Video I/O uses temp files (not pipes) for FFmpeg to avoid pipe-buffer deadlocks on long videos.
- **Resolution scaling**: Style parameters (font size, margins, glow) auto-scale proportionally when resolution differs from the 1080p baseline the presets are authored for.
- **Output naming**: Files are written to ComfyUI's output directory with sequential `WordPop_NNNNN` prefixes.

### Color Handling (styles.py)

ASS uses BGR byte order with alpha: `&HAABBGGRR`. The `hex_to_ass_color()` and `hex_to_ass_tag_color()` helpers convert standard `#RRGGBB` hex to ASS format. Opacity (0.0–1.0) maps to ASS alpha (255–0, inverted).

### FFmpeg Detection (renderer.py)

Searches in order: PATH → bundled `./ffmpeg/` directory → common Windows install locations (`C:/ffmpeg/bin/`, `C:/Program Files/ffmpeg/bin/`, `~/ffmpeg/bin/`).

## Data Flow Types

| Type | Shape / Format | Description |
|------|---------------|-------------|
| `Word` | dataclass(text, start, end, probability) | Single transcribed word with timing |
| `TranscriptResult` | dataclass(words, language, duration) | Full transcription output |
| `WordGroup` | dataclass(words, start, end, text) | Grouped words for display |
| `WordPopStyle` | dataclass (30+ fields) | Complete rendering configuration |
| ComfyUI `AUDIO` | dict: waveform=(B,C,S) tensor, sample_rate=int | Audio input from ComfyUI |
| ComfyUI `IMAGE` | (B,H,W,C) float32 tensor [0,1] | Frame batch, RGB or RGBA |
