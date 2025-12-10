import logging
import threading
from typing import Optional, Tuple

import numpy as np
import cv2
from winocr import recognize_cv2_sync

RapidOCR = None

from subtitle.language_pack_manager import ensure_language_pack

_engine_lock = threading.Lock()
_engines = {}
_language_pack_checked = False


def _ensure_winocr_language_pack(lang: str = "en") -> None:
    """Ensure Windows OCR language pack is installed for the given language."""
    global _language_pack_checked

    if _language_pack_checked:
        return

    with _engine_lock:
        if _language_pack_checked:
            return

        logging.info("Checking Windows OCR language pack for: %s", lang)
        if ensure_language_pack(lang):
            logging.info("Windows OCR language pack ready for: %s", lang)
        else:
            logging.warning(
                "Failed to ensure language pack for: %s. WinOCR may not work properly.",
                lang,
            )

        _language_pack_checked = True


def _get_rapidocr_engine(
    rec_model_path: Optional[str] = None,
    keys_path: Optional[str] = None,
):
    global _engines, RapidOCR

    if RapidOCR is None:
        from rapidocr_onnxruntime import RapidOCR as _RapidOCR

        RapidOCR = _RapidOCR

    config_key = (rec_model_path, keys_path)

    if config_key not in _engines:
        with _engine_lock:
            if config_key not in _engines:
                if rec_model_path:
                    logging.info(
                        "Initializing RapidOCR with Rec model: %s", rec_model_path
                    )
                    _engines[config_key] = RapidOCR(
                        rec_model_path=rec_model_path,
                        keys_path=keys_path,
                        use_det=False,
                    )
                else:
                    logging.info("Initializing default RapidOCR (Det+Rec)")
                    _engines[config_key] = RapidOCR()

    return _engines[config_key]


def _extract_with_winocr(image: np.ndarray, lang: str = "en") -> Tuple[str, float]:
    """Extract text using Windows OCR (WinOCR).

    Args:
        image: Image as numpy array
        lang: Language code for OCR

    Returns:
        Tuple of (text, confidence)
    """

    # Ensure language pack is installed
    _ensure_winocr_language_pack(lang)

    try:
        # Map language codes to WinOCR language tags
        lang_map = {
            "zh-CN": "zh-Hans-CN",
            "zh-cn": "zh-Hans-CN",
            "chinese": "zh-Hans-CN",
            "zh-TW": "zh-Hant-TW",
            "zh-tw": "zh-Hant-TW",
            "ja": "ja",
            "ja-JP": "ja",
            "japanese": "ja",
            "korean": "ko",
            "en": "en",
            "english": "en",
            "ar": "ar",
            "arabic": "ar",
            "fr": "fr",
            "french": "fr",
            "de": "de",
            "german": "de",
            "es": "es",
            "spanish": "es",
            "ru": "ru",
            "russian": "ru",
        }
        winocr_lang = lang_map.get(lang.lower(), "en")

        result = recognize_cv2_sync(image, winocr_lang)

        if isinstance(result, dict):
            text = result.get("text", "").strip()
            # WinOCR doesn't provide confidence, default to 1.0
            confidence = 1.0
            return text, confidence
        elif isinstance(result, str):
            return result.strip(), 1.0
        else:
            return "", 0.0

    except Exception as exc:
        raise RuntimeError(f"WinOCR failed to process image: {exc}") from exc


def _extract_with_rapidocr(
    image: np.ndarray,
    min_confidence: float = 0.55,
    max_lines: int = 2,
    rec_model_path: Optional[str] = None,
    keys_path: Optional[str] = None,
) -> Tuple[str, float]:
    """Extract text using RapidOCR.

    Args:
        image: Image as numpy array
        min_confidence: Minimum confidence threshold
        max_lines: Maximum number of lines to extract
        rec_model_path: Path to recognition model
        keys_path: Path to keys file

    Returns:
        Tuple of (text, confidence)
    """
    engine = _get_rapidocr_engine(rec_model_path, keys_path)
    results, _ = engine(image)

    if not results:
        return "", 0.0

    is_rec_only = rec_model_path is not None

    if is_rec_only:
        # Rec-only format: [[text, confidence], ...]
        usable = [
            item for item in results if len(item) >= 2 and item[1] >= min_confidence
        ]
        if not usable:
            return "", 0.0
        limited = usable[: max(1, max_lines)]
        lines = [entry[0].strip() for entry in limited if entry[0].strip()]
        if not lines:
            return "", 0.0
        avg_conf = float(sum(entry[1] for entry in limited) / len(limited))
    else:
        # Detection mode format: [[box, text, confidence], ...]
        usable = [
            item for item in results if len(item) >= 3 and item[2] >= min_confidence
        ]
        if not usable:
            return "", 0.0
        usable.sort(key=lambda entry: float(np.mean([pt[1] for pt in entry[0]])))
        limited = usable[: max(1, max_lines)]
        lines = [entry[1].strip() for entry in limited if entry[1].strip()]
        if not lines:
            return "", 0.0
        avg_conf = float(sum(entry[2] for entry in limited) / len(limited))

    text = "\n".join(lines)
    return text, avg_conf


def extract_subtitle_text(
    image: np.ndarray,
    *,
    min_confidence: float = 0.55,
    max_lines: int = 2,
    lang: str = "en",
    use_winocr: bool = False,
    rec_model_path: Optional[str] = None,
    keys_path: Optional[str] = None,
    skip_preprocessing: bool = False,
) -> Tuple[str, float, str]:
    """Extract subtitle text from image using WinOCR or RapidOCR.

    Args:
        image: Image as numpy array
        min_confidence: Minimum confidence threshold (for RapidOCR only)
        max_lines: Maximum number of lines to extract (for RapidOCR only)
        lang: Source language for OCR
        use_winocr: Whether to use WinOCR as primary engine
        rec_model_path: Path to recognition model (RapidOCR)
        keys_path: Path to keys file (RapidOCR)
        skip_preprocessing: If True, skip image preprocessing

    Returns:
        Tuple of (text, confidence, engine_name)
    """
    if image is None or image.size == 0:
        return "", 0.0, "None"

    logging.debug("OCR input image shape: %s", image.shape)

    if not use_winocr:
        try:
            # White padding preprocessing for v5 rec-only model (fixes edge character detection)
            padded = cv2.copyMakeBorder(
                image, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=[255, 255, 255]
            )
            text, conf = _extract_with_rapidocr(
                padded,
                min_confidence,
                max_lines,
                rec_model_path=rec_model_path,
                keys_path=keys_path,
            )
            return text, conf, "RapidOCR"
        except Exception as exc:
            logging.error("RapidOCR failed: %s", exc)
            raise RuntimeError(f"RapidOCR failed: {exc}") from exc

    processed_image = image
    if not skip_preprocessing:
        try:
            # 1. Convert to grayscale if needed
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image

            # 2. Apply Otsu's binarization to separate text from background
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # 3. Invert the image
            inverted = cv2.bitwise_not(binary)

            # 4. Add padding (white border) for WinOCR
            padded = cv2.copyMakeBorder(
                inverted, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255
            )

            # 5. Convert back to BGR (3 channels)
            processed_image = cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)

            logging.debug(
                "Applied WinOCR preprocessing: Grayscale -> Otsu -> Invert -> Padding"
            )
        except Exception as e:
            logging.warning("WinOCR preprocessing failed, using original image: %s", e)
            processed_image = image

    try:
        text, conf = _extract_with_winocr(processed_image, lang)
        if text:
            logging.debug("WinOCR extracted text: '%s'", text[:50])
        else:
            logging.debug("WinOCR found no text")
        return text, conf, "WinOCR"
    except Exception as exc:
        logging.error("WinOCR failed: %s", exc)
        raise RuntimeError(f"WinOCR failed to process image: {exc}") from exc
