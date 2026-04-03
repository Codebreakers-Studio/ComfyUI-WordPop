"""ComfyUI node wrapper for WordPop subtitle generator.

Two IMAGE outputs — Transparent Overlay and Video with Subs — ready to wire
directly into VHS_VideoCombine or any other video/image node.

Video decoding uses temp files (not pipes) to avoid deadlocks on long videos.
"""

import copy
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import numpy as np
import torch

logger = logging.getLogger("WordPop")

# ---------------------------------------------------------------------------
# Disable Rich live rendering (deadlocks in ComfyUI)
# ---------------------------------------------------------------------------
import rich.progress as _rp
import rich.console as _rc

_OrigProgress = _rp.Progress
_OrigConsole = _rc.Console


class _SilentProgress(_OrigProgress):
    def __init__(self, *args, **kwargs):
        kwargs["disable"] = True
        kwargs["console"] = _OrigConsole(quiet=True)
        super().__init__(*args, **kwargs)


_rp.Progress = _SilentProgress

# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent

import sys
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from styles import PRESETS, get_preset                        # noqa: E402
from transcriber import transcribe, Word                      # noqa: E402
from subtitle_generator import write_ass                      # noqa: E402
from renderer import (                                        # noqa: E402
    find_ffmpeg,
    find_ffprobe,
    render_overlay,
    render_burned,
    render_preview,
    get_video_resolution,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"\033[96m[WordPop]\033[0m {msg}", flush=True)


def _check_interrupt() -> None:
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
        throw_exception_if_processing_interrupted()
    except (ImportError, AttributeError):
        pass


def _get_temp_dir() -> Path:
    try:
        import folder_paths
        return Path(folder_paths.get_temp_directory())
    except Exception:
        return Path(tempfile.gettempdir())


def _get_output_dir() -> Path:
    try:
        import folder_paths
        return Path(folder_paths.get_output_directory())
    except Exception:
        return Path(tempfile.gettempdir())


def _next_output_prefix(output_dir: Path) -> str:
    """Find the next available WordPop_NNNNN prefix in the output folder."""
    existing = list(output_dir.glob("WordPop_*"))
    max_num = 0
    for f in existing:
        stem = f.stem  # e.g. WordPop_00012_overlay
        parts = stem.split("_")
        if len(parts) >= 2:
            try:
                max_num = max(max_num, int(parts[1]))
            except ValueError:
                pass
    return f"WordPop_{max_num + 1:05d}"


def _uid(prefix: str, ext: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"


def _save_audio(audio_dict: dict, out_path: Path) -> Path:
    """Save ComfyUI AUDIO to WAV via FFmpeg so PyAV can always read it."""
    waveform = audio_dict["waveform"]
    sr = audio_dict["sample_rate"]
    # ComfyUI AUDIO: waveform is (batch, channels, samples)
    if waveform.dim() == 3:
        waveform = waveform[0]  # drop batch → (channels, samples)
    data = waveform.cpu().numpy()  # (channels, samples)
    channels = data.shape[0]
    # Interleave channels: (channels, samples) → (samples * channels,)
    interleaved = data.T.flatten()  # (samples, channels) → flat
    pcm = (interleaved * 32767).clip(-32768, 32767).astype(np.int16)

    # Pipe raw PCM into FFmpeg to produce a proper WAV
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "s16le", "-ar", str(sr), "-ac", str(channels),
        "-i", "-",
        "-c:a", "pcm_s16le",
        str(out_path),
    ]
    proc = subprocess.run(cmd, input=pcm.tobytes(), capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg audio save failed: {proc.stderr.decode()[-300:]}")
    return out_path


def _save_video(images: torch.Tensor, out_path: Path, fps: float = 24.0) -> Path:
    """Save IMAGE tensor to MP4 via temp raw file (no pipe deadlock risk)."""
    ffmpeg = find_ffmpeg()
    b, h, w, c = images.shape
    raw_path = out_path.with_suffix(".raw")
    try:
        # Write raw RGB frames to temp file
        with open(raw_path, "wb") as f:
            for i in range(b):
                frame = images[i]
                if frame.shape[-1] == 4:
                    frame = frame[..., :3]
                f.write((frame.cpu().numpy() * 255).clip(0, 255).astype(np.uint8).tobytes())

        cmd = [
            ffmpeg, "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{w}x{h}", "-pix_fmt", "rgb24", "-r", str(fps),
            "-i", str(raw_path),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{proc.stderr.decode()[-400:]}")
    finally:
        if raw_path.exists():
            try:
                raw_path.unlink()
            except OSError:
                pass
    return out_path


def _video_to_tensor(video_path: Path) -> torch.Tensor:
    """
    Load a video file into a ComfyUI IMAGE tensor (B, H, W, C) float32 [0,1].

    Decodes via FFmpeg to a temp raw file — NOT a pipe — so there is zero
    risk of pipe-buffer deadlock regardless of video length.
    """
    ffprobe = find_ffprobe()
    ffmpeg = find_ffmpeg()

    # Get resolution
    res = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", str(video_path)],
        capture_output=True, text=True, timeout=30,
    )
    parts = res.stdout.strip().split("x")
    w, h = int(parts[0]), int(parts[1])

    # RGBA for overlay formats, RGB for everything else
    ext = video_path.suffix.lower()
    if ext in (".webm", ".mov"):
        pix_fmt, channels = "rgba", 4
    else:
        pix_fmt, channels = "rgb24", 3

    frame_size = w * h * channels

    # Decode to temp raw file (avoids pipe deadlock)
    raw_path = video_path.with_suffix(".raw")
    try:
        _log(f"Decoding {video_path.name} → raw frames...")
        cmd = [
            ffmpeg, "-y",
            "-i", str(video_path),
            "-f", "rawvideo", "-pix_fmt", pix_fmt,
            "-v", "error",
            str(raw_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg decode failed: {proc.stderr.decode()[-300:]}")

        raw_size = raw_path.stat().st_size
        n_frames = raw_size // frame_size
        if n_frames == 0:
            raise RuntimeError(f"No frames decoded from {video_path}")

        _log(f"Reading {n_frames} frames ({raw_size / (1024**2):.1f} MB)...")

        # Read frame by frame to avoid doubling memory
        arr = np.empty((n_frames, h, w, channels), dtype=np.uint8)
        with open(raw_path, "rb") as f:
            for i in range(n_frames):
                chunk = f.read(frame_size)
                if len(chunk) < frame_size:
                    arr = arr[:i]
                    break
                arr[i] = np.frombuffer(chunk, dtype=np.uint8).reshape(h, w, channels)
                if i > 0 and i % 200 == 0:
                    _check_interrupt()
    finally:
        if raw_path.exists():
            try:
                raw_path.unlink()
            except OSError:
                pass

    _log(f"Loaded {arr.shape[0]} frames ({w}x{h}, {'RGBA' if channels == 4 else 'RGB'})")
    return torch.from_numpy(arr).float() / 255.0


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class WordPop:
    """Word-by-word subtitle generator. Outputs IMAGE tensors for VHS etc."""

    CATEGORY = "Codebreakers/Video"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("Transparent_Overlay", "Video_with_Subs", "Overlay_File_Path")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (["tiny", "base", "small", "medium", "large-v3"], {"default": "base"}),
                "device": (["cpu", "cuda"], {"default": "cpu"}),
                "style_preset": (list(PRESETS.keys()), {"default": list(PRESETS.keys())[0]}),
                "mode": (["use_preset", "pop", "karaoke"], {"default": "use_preset"}),
                "aspect_ratio": (["16:9", "9:16"], {"default": "16:9"}),
                "custom_text_override": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Leave empty for Whisper transcription, or paste replacement text.",
                }),
            },
            "optional": {
                "video_frames": ("IMAGE",),
                "audio": ("AUDIO",),
            },
        }

    def execute(
        self,
        model: str,
        device: str,
        style_preset: str,
        mode: str,
        aspect_ratio: str,
        custom_text_override: str,
        audio=None,
        video_frames=None,
    ):
        try:
            import comfy.utils
            pbar = comfy.utils.ProgressBar(6)
        except Exception:
            pbar = None

        def step(n, msg):
            _log(msg)
            if pbar:
                pbar.update_absolute(n, 6)
            _check_interrupt()

        if audio is None and video_frames is None:
            raise ValueError("WordPop needs at least audio or video_frames.")

        step(0, "Starting...")
        tmp = _get_temp_dir()
        tmp.mkdir(parents=True, exist_ok=True)
        out_dir = _get_output_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex[:8]
        prefix = _next_output_prefix(out_dir)  # e.g. WordPop_00001

        # ── Save inputs to temp ──────────────────────────────────────
        audio_path = video_path = None
        has_video = False

        if audio is not None:
            audio_path = tmp / _uid(f"wp_{rid}_a", ".wav")
            _save_audio(audio, audio_path)
            _log(f"Audio → {audio_path.name}")

        if video_frames is not None:
            video_path = tmp / _uid(f"wp_{rid}_v", ".mp4")
            _save_video(video_frames, video_path)
            _log(f"Video → {video_path.name}")
            has_video = True

        transcribe_src = audio_path or video_path

        # Verify the file has an audio stream before sending to Whisper
        _log(f"Transcribe source: {transcribe_src}")
        if transcribe_src and transcribe_src.exists():
            _log(f"  File size: {transcribe_src.stat().st_size} bytes")
            # Quick probe to confirm audio stream exists
            try:
                _ffprobe = find_ffprobe()
                probe = subprocess.run(
                    [_ffprobe, "-v", "error", "-select_streams", "a",
                     "-show_entries", "stream=codec_name,sample_rate,channels",
                     "-of", "csv=p=0", str(transcribe_src)],
                    capture_output=True, text=True, timeout=10,
                )
                _log(f"  Audio streams: {probe.stdout.strip() or 'NONE FOUND'}")
                if not probe.stdout.strip():
                    raise RuntimeError(
                        f"No audio stream in {transcribe_src.name}. "
                        "Make sure you connect an AUDIO input to the WordPop node."
                    )
            except FileNotFoundError:
                pass  # ffprobe not available, let whisper try anyway
        else:
            raise RuntimeError("No input file available for transcription.")

        # ── Resolution ────────────────────────────────────────────────
        if has_video and video_path:
            res = get_video_resolution(video_path)
            resolution = res if res else (1920, 1080)
        else:
            resolution = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)

        # ── Style — scale font to match actual resolution vs 1080p baseline ──
        style = copy.deepcopy(get_preset(style_preset))
        if mode != "use_preset":
            style.mode = mode

        # Presets are authored for 1920×1080.  Scale font_size, margins,
        # and glow proportionally so subs look the same at any resolution.
        ref_h = 1080
        actual_h = resolution[1]
        if actual_h != ref_h:
            scale = actual_h / ref_h
            style.font_size = max(16, int(style.font_size * scale))
            style.margin_v = max(4, int(style.margin_v * scale))
            style.margin_h = max(4, int(style.margin_h * scale))
            style.glow_size = round(style.glow_size * scale, 1)
            _log(f"Scaled style for {actual_h}p: font={style.font_size}px, margins=v{style.margin_v}/h{style.margin_h}")

        _log(f"Style: {style_preset} | Mode: {style.mode} | Font: {style.font_size}px | Res: {resolution[0]}x{resolution[1]}")

        # ── Transcribe ────────────────────────────────────────────────
        step(1, f"Whisper ({model}, {device})...")
        transcript = transcribe(
            audio_path=transcribe_src,
            model_name=model,
            device=device,
            compute_type="int8" if device == "cpu" else "float16",
        )
        words = transcript.words
        duration = transcript.duration
        step(2, f"Transcribed: {len(words)} words, {duration:.1f}s")

        # ── Custom text override ──────────────────────────────────────
        custom = custom_text_override.strip()
        if custom:
            cwords = custom.split()
            if len(cwords) != len(words):
                _log(f"WARNING: custom={len(cwords)} words vs whisper={len(words)}")
            new = []
            for orig, rep in zip(words, cwords):
                new.append(Word(text=rep, start=orig.start, end=orig.end, probability=orig.probability))
            if len(cwords) > len(words):
                last = words[-1] if words else Word(text="", start=0, end=0.5, probability=1.0)
                for i, extra in enumerate(cwords[len(words):]):
                    s = last.end + 0.3 * i
                    new.append(Word(text=extra, start=s, end=s + 0.3, probability=0.5))
            words = new

        # ── Generate ASS (temp) + final outputs (output folder) ─────
        ass_path = tmp / f"wp_{rid}.ass"
        overlay_path = out_dir / f"{prefix}_overlay.mov"
        video_out_path = out_dir / f"{prefix}_subs.mp4"

        step(3, "Generating ASS + rendering overlay (MOV+alpha)...")
        write_ass(words, style, ass_path, resolution)
        render_overlay(ass_path=ass_path, output_path=overlay_path,
                       duration=duration, resolution=resolution, overlay_format="mov")

        _check_interrupt()

        # ── Render video ──────────────────────────────────────────────
        if has_video and video_path:
            step(4, "Burning subs into video...")
            render_burned(video_path, ass_path, video_out_path)
        else:
            step(4, "Rendering preview (subs on black + audio)...")
            render_preview(ass_path=ass_path, audio_path=transcribe_src,
                           output_path=video_out_path, duration=duration,
                           resolution=resolution)

        # ── Load back as IMAGE tensors (temp file, no pipe deadlock) ──
        step(5, "Loading rendered videos into tensors...")
        overlay_tensor = _video_to_tensor(overlay_path)
        video_tensor = _video_to_tensor(video_out_path)

        step(6, f"Done! Overlay: {overlay_tensor.shape[0]} frames, Video: {video_tensor.shape[0]} frames")
        _log(f"Saved to output folder:")
        _log(f"  Overlay: {overlay_path}")
        _log(f"  Video:   {video_out_path}")

        return (overlay_tensor, video_tensor, str(overlay_path))
