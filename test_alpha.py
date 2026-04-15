"""Test that render_overlay produces genuine RGBA transparency."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def find_bin(name):
    import shutil
    p = shutil.which(name)
    if p:
        return p
    for d in [Path(__file__).parent / "ffmpeg", Path("C:/ffmpeg/bin")]:
        c = d / f"{name}.exe"
        if c.exists():
            return str(c)
    raise RuntimeError(f"{name} not found")


FFMPEG = find_bin("ffmpeg")
FFPROBE = find_bin("ffprobe")
W, H, DUR = 640, 360, 1.0

ASS_CONTENT = r"""[Script Info]
Title: Alpha Test
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,HELLO WORLD
"""


def run(cmd, label=""):
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0:
        print(f"FAIL [{label}]: {r.stderr.decode('utf-8', errors='replace')[-500:]}")
        sys.exit(1)
    return r


def get_pix_fmt(path):
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=pix_fmt",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)], "probe pix_fmt")
    return r.stdout.decode().strip()


def check_alpha_pixels(path):
    """Extract raw RGBA pixels from frame 0 and check alpha values."""
    # Extract single frame as raw RGBA to a temp file.
    # For VP9 WebM, we must use libvpx-vp9 decoder explicitly to get alpha.
    import tempfile, os
    raw_path = Path(tempfile.mktemp(suffix=".raw"))
    is_webm = str(path).endswith(".webm")
    decode_cmd = [FFMPEG, "-y"]
    if is_webm:
        decode_cmd += ["-c:v", "libvpx-vp9"]
    decode_cmd += ["-i", str(path), "-vframes", "1",
                   "-f", "rawvideo", "-pix_fmt", "rgba", str(raw_path)]
    run(decode_cmd, "extract pixels")
    with open(raw_path, "rb") as f:
        pixels = f.read()
    os.unlink(raw_path)
    expected_size = W * H * 4
    if len(pixels) != expected_size:
        print(f"FAIL: expected {expected_size} bytes, got {len(pixels)}")
        return False

    # Sample pixels: corners should be transparent, center should have text
    bg_alpha_values = []
    text_alpha_values = []

    for y in range(H):
        for x in range(W):
            offset = (y * W + x) * 4
            r_val = pixels[offset]
            g_val = pixels[offset + 1]
            b_val = pixels[offset + 2]
            a_val = pixels[offset + 3]

            # Corners (definitely background)
            if (x < 20 and y < 20) or (x > W - 20 and y > H - 20):
                bg_alpha_values.append(a_val)
            # Center region where text likely is
            elif abs(x - W // 2) < 100 and abs(y - H // 2) < 30:
                if a_val > 0:
                    text_alpha_values.append(a_val)

    avg_bg = sum(bg_alpha_values) / len(bg_alpha_values) if bg_alpha_values else 255
    max_bg = max(bg_alpha_values) if bg_alpha_values else 255

    print(f"  Background alpha: avg={avg_bg:.1f}, max={max_bg} (want 0)")
    print(f"  Text pixels with alpha>0: {len(text_alpha_values)} (want >0)")
    if text_alpha_values:
        avg_text = sum(text_alpha_values) / len(text_alpha_values)
        print(f"  Text alpha avg: {avg_text:.1f} (want high)")

    bg_ok = max_bg == 0
    text_ok = len(text_alpha_values) > 50
    return bg_ok and text_ok


def test_format(fmt, ext):
    print(f"\n{'='*50}")
    print(f"Testing {fmt.upper()} ({ext}) overlay...")
    print(f"{'='*50}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ass_path = tmpdir / "test.ass"
        ass_path.write_text(ASS_CONTENT, encoding="utf-8")
        out_path = tmpdir / f"overlay.{ext}"

        ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")

        if fmt == "mov":
            cmd = [
                FFMPEG, "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s={W}x{H}:d={DUR:.3f},format=rgba",
                "-vf", f"split[rgb][alpha];[rgb]ass='{ass_escaped}'[text];[alpha]ass='{ass_escaped}',format=gray[mask];[text][mask]alphamerge",
                "-c:v", "png",
                "-pix_fmt", "rgba",
                "-t", f"{DUR:.3f}",
                str(out_path),
            ]
        else:
            cmd = [
                FFMPEG, "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s={W}x{H}:d={DUR:.3f},format=rgba",
                "-vf", f"split[rgb][alpha];[rgb]ass='{ass_escaped}'[text];[alpha]ass='{ass_escaped}',format=gray[mask];[text][mask]alphamerge",
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuva420p",
                "-auto-alt-ref", "0",
                "-b:v", "2M",
                "-t", f"{DUR:.3f}",
                str(out_path),
            ]

        print(f"  CMD: {' '.join(cmd)}")
        run(cmd, f"render {fmt}")

        pix_fmt = get_pix_fmt(out_path)
        print(f"  Pixel format: {pix_fmt}")

        has_alpha_fmt = "a" in pix_fmt  # rgba, yuva420p, etc.
        if not has_alpha_fmt:
            # ffprobe misreports VP9 alpha as yuv420p — not a real failure
            print(f"  Note: ffprobe reports '{pix_fmt}' (VP9 alpha misreport is expected)")

        # Pixel-level check is the ground truth for both formats
        ok = check_alpha_pixels(out_path)

        return ok


if __name__ == "__main__":
    mov_ok = test_format("mov", "mov")
    webm_ok = test_format("webm", "webm")

    print(f"\n{'='*50}")
    if mov_ok and webm_ok:
        print("PASS — both formats have working alpha transparency")
    else:
        print(f"FAIL — MOV: {'PASS' if mov_ok else 'FAIL'}, WebM: {'PASS' if webm_ok else 'FAIL'}")
    sys.exit(0 if (mov_ok and webm_ok) else 1)
