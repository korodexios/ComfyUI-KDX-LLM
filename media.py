"""KDX LLM Client — media helpers: image/audio/video → base64."""

from __future__ import annotations

import base64
import io
import wave
from typing import Optional

try:
    import numpy as np
except ImportError:
    np = None

try:
    from PIL import Image
except ImportError:
    Image = None


def _check_deps():
    """Raise a clear error if required dependencies are missing."""
    missing = []
    if np is None:
        missing.append("numpy")
    if Image is None:
        missing.append("Pillow")
    if missing:
        raise ImportError(
            f"KDX LLM: missing dependencies: {', '.join(missing)}. "
            f"Run: pip install {' '.join(missing)}"
        )


MAX_BATCH_IMAGES = 16


def _to_rgb_uint8(image_tensor):
    """Any single image (H,W), (H,W,1|3|4) or (1,H,W,C), float 0-1 or uint8 -> (H,W,3) uint8."""
    arr = np.asarray(image_tensor)
    if arr.ndim == 4:
        arr = arr[0]
    if arr.ndim == 2:
        arr = arr[:, :, None]
    if np.issubdtype(arr.dtype, np.floating):
        arr = (arr.astype(np.float32) * 255.0).clip(0, 255).astype(np.uint8)
    elif arr.dtype != np.uint8:
        arr = arr.clip(0, 255).astype(np.uint8)
    channels = arr.shape[2]
    if channels == 1:
        arr = np.repeat(arr, 3, axis=2)
    elif channels == 2:  # grey + alpha
        arr = np.repeat(arr[:, :, :1], 3, axis=2)
    elif channels > 3:
        arr = arr[:, :, :3]
    return np.ascontiguousarray(arr)


def image_batch_to_base64_list(image_tensor, max_images: int = MAX_BATCH_IMAGES, max_size: int = 1024) -> list:
    """Every image of a ComfyUI IMAGE batch (B,H,W,C) -> base64 JPEGs (capped)."""
    _check_deps()
    if hasattr(image_tensor, "cpu"):
        image_tensor = image_tensor.cpu().numpy()
    arr = np.asarray(image_tensor)
    frames = arr if arr.ndim == 4 else arr[np.newaxis, ...]
    return [tensor_to_base64(frame, max_size=max_size) for frame in frames[:max_images]]


def tensor_to_base64(image_tensor, max_size: int = 1024, quality: int = 90) -> str:
    """Convert a ComfyUI IMAGE tensor (float32, 0-1) to base64 JPEG.

    Args:
        image_tensor: numpy array or torch tensor, shape (H, W, 3) or (1, H, W, 3)
        max_size: downscale if either dimension exceeds this
        quality: JPEG quality

    Returns:
        base64-encoded JPEG string
    """
    _check_deps()
    # Handle torch tensor
    if hasattr(image_tensor, "cpu"):
        image_tensor = image_tensor.cpu().numpy()

    img_np = _to_rgb_uint8(image_tensor)
    pil_img = Image.fromarray(img_np)

    # Downscale if needed
    w, h = pil_img.size
    if max(w, h) > max_size:
        scale = max_size / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def video_frames_to_base64_list(
    video_tensor,
    frame_step: int = 1,
    max_frames: int = 60,
    max_size: int = 512,
    quality: int = 85,
    sampling_mode: str = "uniform",
    start_frame: int = 0,
    end_frame: int = 0,
) -> list[str]:
    """Convert a video (batch of frames) to a list of base64 JPEGs.

    Args:
        video_tensor: numpy array or torch tensor, shape (B, H, W, 3)
        frame_step: sample every Nth frame (step mode)
        max_frames: max number of frames to include
        max_size: max dimension per frame
        quality: JPEG quality
        sampling_mode: "step" (every Nth), "uniform" (evenly spaced),
                       "start_end" (first N and last M)
        start_frame: for start_end mode — take this many from the beginning
        end_frame: for start_end mode — take this many from the end

    Returns:
        List of base64 strings (may be shorter than input if max_frames hit)
    """
    _check_deps()
    if hasattr(video_tensor, "cpu"):
        video_tensor = video_tensor.cpu().numpy()

    # Shape: (B, H, W, C) or (H, W, C)
    if video_tensor.ndim == 3:
        video_tensor = video_tensor[np.newaxis, ...]

    total = video_tensor.shape[0]

    if sampling_mode == "step":
        # Every Nth frame
        frames = video_tensor[::frame_step]

    elif sampling_mode == "start_end":
        # First N + last M frames
        n_start = min(start_frame, total) if start_frame > 0 else 0
        n_end = min(end_frame, total) if end_frame > 0 else 0
        # Avoid overlap
        if n_start + n_end > total:
            n_end = max(0, total - n_start)
        indices = list(range(n_start)) + list(range(total - n_end, total)) if n_end > 0 else list(range(n_start))
        frames = video_tensor[indices] if indices else video_tensor[:1]

    else:
        # "uniform" (default) — evenly spaced across the whole video
        frames = video_tensor

    # Cap at max_frames (evenly spaced)
    if len(frames) > max_frames:
        indices = np.linspace(0, len(frames) - 1, max_frames, dtype=int)
        frames = frames[indices]

    return [tensor_to_base64(f, max_size=max_size, quality=quality) for f in frames]


def audio_to_wav_base64(
    audio_tensor,
    sample_rate: int = 44100,
    max_seconds: float = 30.0,
) -> str:
    """Convert a ComfyUI AUDIO dict to base64 WAV.

    Args:
        audio_tensor: dict with "waveform" (torch tensor [B, C, samples] or
                      [C, samples]) and "sample_rate" (int)
        max_seconds: trim audio to this many seconds

    Returns:
        base64-encoded WAV string
    """
    _check_deps()
    waveform = audio_tensor["waveform"]
    sr = audio_tensor.get("sample_rate", sample_rate)

    if hasattr(waveform, "cpu"):
        waveform = waveform.cpu().numpy()

    # ComfyUI AUDIO waveforms are [B, C, samples]; drop the batch dim
    # (same pattern as tensor_to_base64 for 4D images). Also accept
    # [C, samples] and [samples] from other producers.
    if waveform.ndim == 3:
        waveform = waveform[0]
    elif waveform.ndim == 1:
        waveform = waveform[np.newaxis, :]

    # Trim to max_seconds (shape is now guaranteed (C, samples))
    max_samples = int(max_seconds * sr)
    if waveform.shape[1] > max_samples:
        waveform = waveform[:, :max_samples]

    # Convert to 16-bit PCM
    if waveform.dtype == np.float32 or waveform.dtype == np.float64:
        # Assume -1.0 to 1.0 range
        waveform = (waveform * 32767).clip(-32768, 32767).astype(np.int16)
    elif waveform.dtype == np.float16:
        waveform = (waveform * 32767).clip(-32768, 32767).astype(np.int16)

    # Write to WAV in memory
    buf = io.BytesIO()
    n_channels = waveform.shape[0]

    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sr)
        # Wave requires interleaved: (samples, channels)
        if n_channels == 1:
            wf.writeframes(waveform[0].tobytes())
        else:
            interleaved = waveform.T.tobytes()
            wf.writeframes(interleaved)

    return base64.b64encode(buf.getvalue()).decode("utf-8")


def build_user_content(
    prompt: str,
    image: Optional[np.ndarray] = None,
    audio: Optional[dict] = None,
    video: Optional[np.ndarray] = None,
    media_mode: str = "none",
    video_frame_step: int = 1,
    video_max_frames: int = 60,
    video_max_size: int = 512,
    audio_max_seconds: float = 30.0,
    video_sampling_mode: str = "uniform",
    video_start_frame: int = 0,
    video_end_frame: int = 0,
) -> object:
    """Build the user message content for the chat API.

    Returns either a string (text only) or a list of content parts
    (multi-modal).
    """
    if media_mode == "none" or (image is None and audio is None and video is None):
        return prompt

    parts = []

    # Text always first
    parts.append({"type": "text", "text": prompt})

    if media_mode == "image" and image is not None:
        # A batch sends every image (up to MAX_BATCH_IMAGES), not just the first.
        for b64 in image_batch_to_base64_list(image):
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )

    elif media_mode == "video" and video is not None:
        frames_b64 = video_frames_to_base64_list(
            video,
            frame_step=video_frame_step,
            max_frames=video_max_frames,
            max_size=video_max_size,
            sampling_mode=video_sampling_mode,
            start_frame=video_start_frame,
            end_frame=video_end_frame,
        )
        for b64 in frames_b64:
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )

    elif media_mode == "audio" and audio is not None:
        b64 = audio_to_wav_base64(audio, max_seconds=audio_max_seconds)
        parts.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": b64,
                    "format": "wav",
                },
            }
        )

    return parts
