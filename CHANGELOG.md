# Changelog

All notable changes to ComfyUI-WordPop will be documented in this file.

## [0.1.0] - 2026-04-03

### Dev Beta — Initial Release

**Core Features**
- Word-by-word subtitle generation using faster-whisper AI transcription
- Pop mode with scale + glow animation per word/group
- Karaoke mode with progressive word-fill highlighting
- 6 built-in style presets: neon, clean, bold, minimal, fire, boxed
- Transparent overlay rendering (WebM VP9+alpha, MOV PNG+alpha)
- Preview video rendering (subtitles on black background with audio)
- Burned-in video rendering (subtitles composited onto source video)
- ASS subtitle file export

**ComfyUI Node**
- Word Pop Subtitles node under Codebreakers/Video category
- IMAGE tensor outputs (Transparent_Overlay, Video_with_Subs)
- Overlay file path string output
- AUDIO and IMAGE (video frames) inputs
- Whisper model selection (tiny, base, small, medium, large-v3)
- CPU and CUDA device support
- 16:9 and 9:16 aspect ratio support
- Auto-scaling of styles to match input resolution
- Custom text override (replace transcription, keep AI timing)
- ComfyUI progress bar integration
- Interrupt support via ComfyUI's processing model

**Standalone CLI**
- Interactive batch file launcher (Word-Pop.bat)
- One-click installer (INSTALL.bat) with auto FFmpeg download
- Full CLI with style overrides, model selection, and output options
- Style save/load to JSON
