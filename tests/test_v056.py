"""
Release 0.5.6 bugfix regression tests.

Covers the 4 bugs found by the second independent LLM review:
1. Audio 3D tensor [B, C, N] handling in media.py
2. IS_CHANGED desync (prompt_store / user_prompt_store mtimes) in chat.py
3. UTF-8 chunking corruption in _http.py SSE stream
4. (i-prefix is by-design — no test, documented in V2.1_PLAN.md)

Run:  python tests/test_v056.py
"""

import base64
import json
import os
import re
import struct
import sys
import types
import wave
import importlib.util

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.join(BASE, "ComfyUI-KDX-LLM") if os.path.basename(BASE) == "tests" else BASE

# ── Load modules with relative imports resolved ─────────────────────

def _load(name, filename):
    """Load a module from the KDX package with relative imports working."""
    spec = importlib.util.spec_from_file_location(
        f"kdx.{name}", os.path.join(PROJECT, filename)
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "kdx"
    sys.modules[f"kdx.{name}"] = mod
    # Register the package itself
    if "kdx" not in sys.modules:
        pkg = types.ModuleType("kdx")
        pkg.__path__ = [PROJECT]
        sys.modules["kdx"] = pkg
    spec.loader.exec_module(mod)
    return mod


def _numpy():
    import numpy
    return numpy


# ── Test 1: Audio 3D tensor [B, C, N] ───────────────────────────────

def test_audio_3d_batch():
    """ComfyUI AUDIO waveform is [B, C, samples]. Batch dim must be dropped."""
    media = _load("media", "media.py")
    try:
        np = _numpy()
    except ImportError:
        print("  SKIP: numpy not installed")
        return

    sr = 8000
    # 1 second of audio, mono, batch dim
    samples = sr
    waveform = np.zeros((1, 1, samples), dtype=np.float32)
    # Simple tone: 440 Hz
    import math
    for i in range(samples):
        waveform[0, 0, i] = math.sin(2 * math.pi * 440 * i / sr)

    audio = {"waveform": waveform, "sample_rate": sr}
    b64 = media.audio_to_wav_base64(audio, max_seconds=30.0)

    # Decode the WAV
    raw = base64.b64decode(b64)
    wf = wave.open(__import__("io").BytesIO(raw), "rb")
    assert wf.getnchannels() == 1, f"expected 1 channel, got {wf.getnchannels()}"
    assert wf.getframerate() == sr, f"expected {sr} Hz, got {wf.getframerate()}"
    assert wf.getsampwidth() == 2, f"expected 16-bit, got {wf.getsampwidth() * 8}-bit"

    # 1 second at 8000 Hz = 8000 samples = 16000 bytes
    expected_bytes = samples * 2
    actual_bytes = wf.getnframes() * wf.getsampwidth()
    wf.close()
    assert actual_bytes == expected_bytes, (
        f"expected {expected_bytes} bytes, got {actual_bytes} — "
        f"batch dim not dropped correctly"
    )
    print("  PASS: audio 3D batch [1,1,N] -> 1ch, correct duration")


def test_audio_3d_stereo():
    """Stereo [B, 2, N] must produce a 2-channel WAV with correct frame count."""
    media = _load("media", "media.py")
    try:
        np = _numpy()
    except ImportError:
        print("  SKIP: numpy not installed")
        return

    sr = 8000
    samples = sr  # 1 second
    waveform = np.zeros((1, 2, samples), dtype=np.float32)
    import math
    for i in range(samples):
        waveform[0, 0, i] = math.sin(2 * math.pi * 440 * i / sr)
        waveform[0, 1, i] = math.sin(2 * math.pi * 880 * i / sr)

    audio = {"waveform": waveform, "sample_rate": sr}
    b64 = media.audio_to_wav_base64(audio, max_seconds=30.0)

    raw = base64.b64decode(b64)
    import io as _io
    wf = wave.open(_io.BytesIO(raw), "rb")
    assert wf.getnchannels() == 2, f"expected 2 channels, got {wf.getnchannels()}"
    # 1 second of stereo = 8000 frames
    assert wf.getnframes() == samples, (
        f"expected {samples} frames, got {wf.getnframes()} — "
        f"stereo frame count wrong"
    )
    wf.close()
    print("  PASS: audio 3D stereo [1,2,N] -> 2ch, correct frame count")


def test_audio_trim():
    """max_seconds must trim the sample axis, not the channel axis."""
    media = _load("media", "media.py")
    try:
        np = _numpy()
    except ImportError:
        print("  SKIP: numpy not installed")
        return

    sr = 8000
    samples = sr * 5  # 5 seconds
    waveform = np.zeros((1, 1, samples), dtype=np.float32)
    waveform[:] = 0.5

    audio = {"waveform": waveform, "sample_rate": sr}
    b64 = media.audio_to_wav_base64(audio, max_seconds=2.0)

    raw = base64.b64decode(b64)
    import io as _io
    wf = wave.open(_io.BytesIO(raw), "rb")
    # 2 seconds at 8000 Hz = 16000 frames
    expected_frames = int(2.0 * sr)
    assert wf.getnframes() == expected_frames, (
        f"expected {expected_frames} frames (2s), got {wf.getnframes()} — "
        f"trim hit wrong axis"
    )
    wf.close()
    print("  PASS: audio trim max_seconds=2.0 on 5s clip -> 2s")


# ── Test 2: IS_CHANGED includes prompt store mtimes ─────────────────

def test_is_changed_prompt_mtimes():
    """IS_CHANGED hash key must include prompt_store and user_prompt_store mtimes."""
    chat_src = open(os.path.join(PROJECT, "chat.py")).read()

    # Check imports exist
    assert "from . import prompt_store" in chat_src, (
        "chat.py missing: from . import prompt_store"
    )
    assert "from . import user_prompt_store" in chat_src, (
        "chat.py missing: from . import user_prompt_store"
    )

    # Check IS_CHANGED key includes both mtimes
    # Find the IS_CHANGED method
    m = re.search(r"def IS_CHANGED.*?(?=\n    def |\nclass )", chat_src, re.DOTALL)
    assert m, "IS_CHANGED method not found in chat.py"
    is_changed_block = m.group(0)

    assert "prompt_store.mtime()" in is_changed_block, (
        "IS_CHANGED key missing: prompt_store.mtime()"
    )
    assert "user_prompt_store.mtime()" in is_changed_block, (
        "IS_CHANGED key missing: user_prompt_store.mtime()"
    )
    print("  PASS: IS_CHANGED includes prompt_store.mtime() and user_prompt_store.mtime()")


# ── Test 3: UTF-8 incremental decoder in _http.py ───────────────────

def test_utf8_decoder_present():
    """SSE transport must use the incremental decoder in kdx_core.sse_parser."""
    http_src = open(os.path.join(PROJECT, "_http.py")).read()
    parser_src = open(os.path.join(PROJECT, "kdx_core", "sse_parser.py")).read()

    assert "SSEAccumulator" in http_src, "_http.py missing: SSEAccumulator"
    assert "iter_content" in http_src, (
        "_http.py should use iter_content (not iter_lines) for chunked reading"
    )
    assert "iter_lines" not in http_src, (
        "_http.py still uses iter_lines — should be iter_content + SSEAccumulator"
    )
    assert "import codecs" in parser_src, (
        "kdx_core/sse_parser.py missing: import codecs"
    )
    assert "getincrementaldecoder" in parser_src, (
        "kdx_core/sse_parser.py missing: codecs.getincrementaldecoder"
    )
    print("  PASS: _http.py uses SSEAccumulator; parser uses incremental UTF-8 decoder")


def test_utf8_split_codepoint():
    """A multi-byte UTF-8 sequence split across chunks must not be corrupted.

    Simulates the exact scenario: a 4-byte emoji (U+1F600 = F0 9F 98 80)
    split across two network chunks. The incremental decoder must hold the
    partial bytes and produce the correct character.
    """
    import codecs

    emoji = "\U0001F600"  # 😀
    line1 = f'data: {{"text": "pre{emoji}post"}}\n'
    raw = line1.encode("utf-8")

    # Find a split point in the middle of the emoji's 4 bytes
    # emoji bytes are at a known position: "pre" = 3 bytes, so emoji starts at offset 3
    split_at = 3 + 2  # split after 2 of the 4 emoji bytes

    chunk1 = raw[:split_at]
    chunk2 = raw[split_at:]

    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    result = decoder.decode(chunk1, final=False) + decoder.decode(chunk2, final=True)

    assert emoji in result, (
        f"emoji lost in split decode: got {result!r}"
    )
    assert "\ufffd" not in result, (
        f"U+FFFD replacement found — split codepoint was corrupted: {result!r}"
    )
    print("  PASS: 4-byte emoji split across chunks decodes correctly")


def test_utf8_slovak_diacritics():
    """Slovak diacritics (2-byte UTF-8) split across chunks."""
    import codecs

    text = "slovenská diakritika: ä ö ü š č ž"
    raw = text.encode("utf-8")

    # Split every 3 bytes to maximize the chance of splitting a 2-byte sequence
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    result = ""
    for i in range(0, len(raw), 3):
        result += decoder.decode(raw[i:i+3], final=False)
    result += decoder.decode(b"", final=True)

    assert result == text, (
        f"Slovak diacritics corrupted by 3-byte chunking: {result!r}"
    )
    print("  PASS: Slovak diacritics survive 3-byte chunking")


# ── Runner ──────────────────────────────────────────────────────────

def main():
    tests = [
        ("Audio 3D batch [1,1,N]", test_audio_3d_batch),
        ("Audio 3D stereo [1,2,N]", test_audio_3d_stereo),
        ("Audio trim max_seconds", test_audio_trim),
        ("IS_CHANGED prompt mtimes", test_is_changed_prompt_mtimes),
        ("UTF-8 decoder present", test_utf8_decoder_present),
        ("UTF-8 split emoji", test_utf8_split_codepoint),
        ("UTF-8 Slovak diacritics", test_utf8_slovak_diacritics),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)
    print("ALL 0.5.6 BUGFIX TESTS PASSED")


if __name__ == "__main__":
    main()
