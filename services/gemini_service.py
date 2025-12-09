import logging
import os
from typing import List, Optional, Dict, Any, Tuple
from PIL import Image
import numpy as np
import time
import imagehash
from google import genai
from google.genai import types

from core.config_manager import ConfigManager
from subtitle.utils import build_image_translation_prompt, encode_image_to_bytes
from threads.translation_errors import TranslationServiceError
from threads.translation_interface import TranslationService


class GeminiTranslationService(TranslationService):
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        configured_model = (self.config.gemini_model or "").strip()
        self.model_name = configured_model
        self.model_capabilities: Dict[str, bool] = {}

        self._gemini_api_keys = self._initialize_api_keys()
        if not self._gemini_api_keys:
            raise ValueError("No Gemini API keys available for translation service")

        self._current_key_index = 0
        self._key_cooldowns: Dict[str, float] = {}
        self._set_client_api_key(self._gemini_api_keys[self._current_key_index])

    def _initialize_api_keys(self) -> List[str]:
        keys: List[str] = []
        primary = (self.config.gemini_api_key or "").strip()
        if primary:
            keys.append(primary)

        fallback_pool = os.getenv("GEMINI_API_KEY_POOL", "")
        for fallback in fallback_pool.split(","):
            candidate = fallback.strip()
            if candidate and candidate not in keys:
                keys.append(candidate)

        return keys

    def _mask_key(self, api_key: str) -> str:
        if not api_key:
            return ""
        if len(api_key) <= 8:
            return api_key
        return f"{api_key[:4]}...{api_key[-4:]}"

    def _set_client_api_key(self, api_key: str) -> None:
        if api_key != self.config.gemini_api_key:
            self.config.gemini_api_key = api_key
            logging.info("Gemini API key rotated to %s", self._mask_key(api_key))
        self.client = genai.Client(api_key=api_key)

    def _keys_rotation_order(self) -> List[str]:
        if not self._gemini_api_keys:
            return []
        return (
            self._gemini_api_keys[self._current_key_index :]
            + self._gemini_api_keys[: self._current_key_index]
        )

    def _is_key_available(self, api_key: str) -> bool:
        cooldown_until = self._key_cooldowns.get(api_key)
        if cooldown_until is None:
            return True
        if time.time() >= cooldown_until:
            del self._key_cooldowns[api_key]
            return True
        return False

    def _mark_key_cooldown(self, api_key: str) -> None:
        self._key_cooldowns[api_key] = time.time() + self.config.cooldown_seconds

    def _advance_index(self, api_key: str) -> None:
        if api_key in self._gemini_api_keys:
            self._current_key_index = (self._gemini_api_keys.index(api_key) + 1) % len(
                self._gemini_api_keys
            )

    def _remove_key(self, api_key: str) -> None:
        if api_key in self._gemini_api_keys:
            logging.warning(
                "Removing Gemini API key %s from rotation due to invalid credentials.",
                self._mask_key(api_key),
            )
            self._gemini_api_keys.remove(api_key)
            self._key_cooldowns.pop(api_key, None)
            if not self._gemini_api_keys:
                raise ValueError("All Gemini API keys are invalid or unavailable")
            self._current_key_index %= len(self._gemini_api_keys)

    def _translate_image(
        self, image: np.ndarray, history: Optional[List[str]] = None
    ) -> str:
        prompt = build_image_translation_prompt(
            target_lang=self.config.target_language, history=history
        )

        model_name = self.model_name
        try:
            cfg_kwargs = {
                "max_output_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
            }

            # Disable safety settings to reduce latency
            safety_settings = [
                types.SafetySetting(
                    category=cat, threshold=types.HarmBlockThreshold.BLOCK_NONE
                )
                for cat in (
                    types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                )
            ]
            cfg_kwargs["safety_settings"] = safety_settings

            img_bytes = encode_image_to_bytes(image)

            gen_config = types.GenerateContentConfig(**cfg_kwargs)
            response = self.client.models.generate_content(
                model=model_name,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                ],
                config=gen_config,
            )
            result = (response.text or "").strip()
            if not result:
                return ""
            return result
        except Exception as exc:
            logging.error("Image translation failed with model %s: %s", model_name, exc)
            raise TranslationServiceError(str(exc)) from exc

    def get_or_translate(
        self,
        region: tuple,
        history: Optional[List[str]] = None,
        last_hash: Optional[Any] = None,
        cache: Optional[Dict] = None,
        screenshot_np: Optional[np.ndarray] = None,
        precomputed_ocr: Optional[Tuple[str, float, float]] = None,
    ) -> Tuple[str, Optional[Any]]:
        if cache is None:
            cache = {}

        if screenshot_np is None:
            logging.error(
                "Gemini service requires a pre-captured frame for translation."
            )
            return "", None

        # Use precomputed OCR for logging if available (optional)
        if precomputed_ocr is not None:
            ocr_text, ocr_conf, ocr_duration_ms = precomputed_ocr
            logging.debug(
                "Using precomputed OCR: text='%s', confidence=%.2f, duration=%.1f ms",
                ocr_text,
                ocr_conf,
                ocr_duration_ms,
            )

        try:
            img_for_hash = Image.fromarray(screenshot_np)
            current_hash = imagehash.phash(img_for_hash)
            if current_hash == last_hash:
                return "", None
            if current_hash in cache:
                return cache[current_hash], current_hash
        except Exception as e:
            logging.error(f"Failed to hash image: {e}")
            current_hash = None

        result = ""
        translation_duration_ms = 0.0

        # Perform image-based translation
        translate_start = time.perf_counter()
        try:
            result = self._translate_with_failover(screenshot_np, history)
        except TranslationServiceError:
            translation_duration_ms = (time.perf_counter() - translate_start) * 1000
            raise
        translation_duration_ms = (time.perf_counter() - translate_start) * 1000

        if result and result != "__NO_TEXT__":
            logging.info(
                "Gemini Image translation completed in %.1f ms: %s",
                translation_duration_ms,
                result,
            )
        else:
            logging.debug(
                "Gemini Image translation returned empty in %.1f ms.",
                translation_duration_ms,
            )

        if current_hash and result and result != "__NO_TEXT__":
            cache[current_hash] = result
            if len(cache) > self.config.max_cache_size:
                oldest_key = next(iter(cache))
                del cache[oldest_key]

        return result, current_hash

    def switch_service(self, service_name: str) -> bool:
        # This service only handles Gemini, so switching is not applicable
        return service_name == "gemini"

    # ------------------------------------------------------------------
    # Error handling helpers
    # ------------------------------------------------------------------
    def _translate_with_failover(
        self, image: np.ndarray, history: Optional[List[str]]
    ) -> str:
        keys_to_try = self._keys_rotation_order()
        if not keys_to_try:
            raise TranslationServiceError("No Gemini API key available")

        last_error: Optional[TranslationServiceError] = None
        for api_key in keys_to_try:
            if api_key not in self._gemini_api_keys:
                continue
            if not self._is_key_available(api_key):
                continue

            self._current_key_index = self._gemini_api_keys.index(api_key)
            self._set_client_api_key(api_key)

            try:
                return self._translate_image(image, history)
            except TranslationServiceError as exc:
                last_error = exc
                self._handle_provider_error(api_key, exc)
                continue

        if last_error is not None:
            raise last_error
        raise TranslationServiceError(
            "All Gemini API keys are cooling down; retry later"
        )

    def _handle_provider_error(
        self, api_key: str, exc: TranslationServiceError
    ) -> None:
        detail = str(exc).lower()
        if "permission" in detail or "invalid" in detail or "unauthorized" in detail:
            self._remove_key(api_key)
            return

        self._mark_key_cooldown(api_key)
        self._advance_index(api_key)
