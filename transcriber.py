"""Audio transcription with word-level timestamps using faster-whisper."""

from dataclasses import dataclass
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn


@dataclass
class Word:
    """A single transcribed word with timing."""
    text: str
    start: float  # seconds
    end: float    # seconds
    probability: float


@dataclass
class TranscriptResult:
    """Full transcription result."""
    words: list[Word]
    language: str
    duration: float  # total audio duration in seconds


def transcribe(
    audio_path: Path,
    model_name: str = "base",
    language: str | None = None,
    device: str = "cpu",
    compute_type: str = "int8",
) -> TranscriptResult:
    """
    Transcribe audio file and return word-level timestamps.

    Args:
        audio_path: Path to audio or video file (FFmpeg handles extraction).
        model_name: Whisper model size (tiny, base, small, medium, large-v3).
        language: Language code (e.g. 'en'). None = auto-detect.
        device: 'cpu' or 'cuda'.
        compute_type: Quantization type. 'int8' for CPU, 'float16' for CUDA.

    Returns:
        TranscriptResult with word-level timestamps.
    """
    from faster_whisper import WhisperModel

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Loading model…"),
        transient=True,
    ) as progress:
        progress.add_task("load", total=None)
        model = WhisperModel(model_name, device=device, compute_type=compute_type)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Transcribing…", total=100)

        segments_iter, info = model.transcribe(
            str(audio_path),
            language=language,
            word_timestamps=True,
            vad_filter=True,
        )

        duration = info.duration
        detected_lang = info.language
        words: list[Word] = []

        for segment in segments_iter:
            if segment.words:
                for w in segment.words:
                    words.append(Word(
                        text=w.word.strip(),
                        start=w.start,
                        end=w.end,
                        probability=w.probability,
                    ))
            # Update progress based on segment timing
            if duration > 0:
                pct = min(100, (segment.end / duration) * 100)
                progress.update(task, completed=pct)

        progress.update(task, completed=100, description="Transcription complete")

    # Filter out empty words
    words = [w for w in words if w.text]

    if not words:
        raise RuntimeError(
            "No words detected in audio. The file may be silent, "
            "corrupt, or in an unsupported format."
        )

    return TranscriptResult(words=words, language=detected_lang, duration=duration)
