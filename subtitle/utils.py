import base64
from typing import List, Optional

import cv2
import numpy as np

from .prompts import simple_translation_prompt


def build_image_translation_prompt(
    target_lang: str = "English",
    source_lang: str = "Auto",
    history: Optional[List[str]] = None,
    history_limit: int = 3,
) -> str:
    prompt_template = simple_translation_prompt.strip()

    lang_map = {
        "en": "English",
        "ar": "Arabic",
        "ja": "Japanese",
        "zh": "Chinese",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "ru": "Russian",
    }
    full_target_lang = lang_map.get(target_lang.lower(), target_lang)
    full_source_lang = lang_map.get(source_lang.lower(), source_lang)

    prompt = prompt_template.format(
        target_lang=full_target_lang, source_lang=full_source_lang
    )

    if history:
        trimmed_history = [item.strip() for item in history if item and item.strip()]
        if trimmed_history:
            recent_context = trimmed_history[-history_limit:]
            context_lines = [
                "\nContext subtitles for consistency only; do not repeat them explicitly:",
                *[f"- {line}" for line in recent_context],
            ]
            prompt += "\n" + "\n".join(context_lines)

    return prompt


def prepare_ocr_image(
    image: np.ndarray,
    max_width: Optional[int] = None,
    min_width: int = 600,
) -> np.ndarray:
    """Resize image for OCR using OpenCV.

    Args:
        image: Input image as numpy array.
        max_width: Maximum allowed width.
        min_width: Minimum desired width.
    """
    if image is None or image.size == 0:
        return image

    height, width = image.shape[:2]
    scale = 1.0

    # 1. Calculate Scale
    if max_width and width > max_width:
        # Downsample
        scale = max_width / width

    # 2. Early Exit if no resizing needed
    if scale == 1.0:
        return image

    # 3. Resize (Lanczos)
    # cv2.INTER_LANCZOS4 is the equivalent of PIL.Image.LANCZOS
    new_width = int(width * scale)
    new_height = int(height * scale)

    return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)


def encode_image_to_base64(image: np.ndarray, quality: int = 70) -> str:
    """Encode numpy image to base64 string (JPEG format) using OpenCV."""
    if image is None or image.size == 0:
        return ""

    success, buffer = cv2.imencode(
        ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    )

    if not success:
        return ""

    return base64.b64encode(buffer).decode("utf-8")


def encode_image_to_bytes(image: np.ndarray, quality: int = 70) -> bytes:
    """Encode numpy image to JPEG bytes using OpenCV."""
    if image is None or image.size == 0:
        return b""

    success, buffer = cv2.imencode(
        ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    )

    if not success:
        return b""

    return buffer.tobytes()
