"""KDX LLM Client — media settings node.

Separate node for audio/video parameters. Wire into Chat node.
Image stays directly in the Chat node (single image, no extra config needed).
"""


class KDX_LLM_Media_Settings:
    """Audio/video media settings for the LLM Chat node."""

    DESCRIPTION = "Sends audio or video (as frames) to a multi-modal model. Connect AUDIO / video frames here and 'media_settings' to Chat. For a single image use Chat's image input directly."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("KDX_LLM_MEDIA",)
    RETURN_NAMES = ("media_settings",)
    FUNCTION = "execute"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # ── Video ──
                "video_sampling_mode": (["uniform", "step", "start_end"], {
                    "default": "uniform",
                    "tooltip": "uniform = evenly spaced across the video, step = every Nth frame, start_end = first N + last N frames",
                }),
                "video_frame_step": ("INT", {"default": 1, "min": 1, "max": 100,
                    "tooltip": "Step mode: sample every Nth frame (1 = all frames)"}),
                "video_start_frames": ("INT", {"default": 0, "min": 0, "max": 500,
                    "tooltip": "start_end mode: take this many frames from the beginning"}),
                "video_end_frames": ("INT", {"default": 0, "min": 0, "max": 500,
                    "tooltip": "start_end mode: take this many frames from the end"}),
                "video_max_frames": ("INT", {"default": 60, "min": 1, "max": 500,
                    "tooltip": "Max frames to send to the API"}),
                "video_max_size": ("INT", {"default": 512, "min": 64, "max": 2048,
                    "tooltip": "Max dimension per frame (pixels)"}),

                # ── Audio ──
                "audio_max_seconds": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 600.0, "step": 1.0,
                    "tooltip": "Trim audio to N seconds"}),
            },
            "optional": {
                # Media inputs — wire here, they pass through to Chat
                "video": ("IMAGE", {
                    "tooltip": "Video frames (batch of IMAGE)"}),
                "audio": ("AUDIO", {
                    "tooltip": "Audio clip (AUDIO tensor)"}),
            },
        }

    def execute(
        self,
        video_sampling_mode="uniform",
        video_frame_step=1,
        video_start_frames=0,
        video_end_frames=0,
        video_max_frames=60,
        video_max_size=512,
        audio_max_seconds=30.0,
        video=None,
        audio=None,
    ):
        media = {
            "video_sampling_mode": video_sampling_mode,
            "video_frame_step": video_frame_step,
            "video_start_frames": video_start_frames,
            "video_end_frames": video_end_frames,
            "video_max_frames": video_max_frames,
            "video_max_size": video_max_size,
            "audio_max_seconds": audio_max_seconds,
            "video": video,
            "audio": audio,
        }
        return (media,)


NODE_CLASS_MAPPINGS = {
    "KDX_LLM_Media_Settings": KDX_LLM_Media_Settings,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KDX_LLM_Media_Settings": "🎬 KDX • LLM Media Settings",
}
