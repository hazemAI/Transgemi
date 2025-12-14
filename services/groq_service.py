import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import imagehash
import numpy as np
from PIL import Image
from openai import OpenAI

from core.config_manager import ConfigManager
from subtitle.utils import build_image_translation_prompt, encode_image_to_base64
from threads.translation_interface import TranslationService


class GroqTranslationService(TranslationService):
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self._groq_api_keys = self._initialize_api_keys()
        if not self._groq_api_keys:
            raise ValueError("No Groq API keys available for translation service")

        self._current_key_index = 0
        self._set_client_api_key(self._groq_api_keys[self._current_key_index])
        self._key_cooldowns: Dict[str, float] = {}

    def _initialize_api_keys(self) -> List[str]:
        keys: List[str] = []
        primary = (self.config.groq_api_key or "").strip()
        if primary:
            keys.append(primary)

        fallback_pool = os.getenv("GROQ_API_KEY_POOL", "")
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
        if api_key != self.config.groq_api_key:
            self.config.groq_api_key = api_key
            logging.info("Groq API key rotated to %s", self._mask_key(api_key))
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.config.groq_base_url,
            max_retries=0,
        )

    def _keys_rotation_order(self) -> List[str]:
        if not self._groq_api_keys:
            return []
        rotation = (
            self._groq_api_keys[self._current_key_index :]
            + self._groq_api_keys[: self._current_key_index]
        )
        return rotation

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
        if api_key in self._groq_api_keys:
            self._current_key_index = (self._groq_api_keys.index(api_key) + 1) % len(
                self._groq_api_keys
            )

    def _remove_key(self, api_key: str) -> None:
        if api_key in self._groq_api_keys:
            logging.warning(
                "Removing Groq API key %s from rotation due to invalid credentials.",
                self._mask_key(api_key),
            )
            self._groq_api_keys.remove(api_key)
            self._key_cooldowns.pop(api_key, None)
            if not self._groq_api_keys:
                raise ValueError("All Groq API keys are invalid or unavailable")
            self._current_key_index %= len(self._groq_api_keys)

    def _translate_image(
        self, image_b64: str, history: Optional[List[str]] = None
    ) -> str:
        if not image_b64:
            return ""

        prompt = build_image_translation_prompt(
            target_lang=self.config.target_language,
            source_lang=self.config.source_language,
            history=history,
        )

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ]

        model_name = self.config.groq_model
        keys_to_try = [
            key for key in self._keys_rotation_order() if self._is_key_available(key)
        ]
        if not keys_to_try:
            return ""

        for api_key in keys_to_try:
            self._set_client_api_key(api_key)
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    top_p=self.config.top_p,
                    frequency_penalty=self.config.frequency_penalty,
                    presence_penalty=self.config.presence_penalty,
                    stream=False,
                )
                content = (
                    response.choices[0].message.content if response.choices else ""
                )
                result = content.strip() if isinstance(content, str) else ""
                if result:
                    return result
            except Exception as exc:
                logging.debug("Groq image translation failed: %s", exc)
                self._handle_provider_error(api_key, exc)
                continue

        return ""

    def get_or_translate(
        self,
        region: tuple,
        history: Optional[List[str]] = None,
        last_hash: Optional[Any] = None,
        cache: Optional[Dict[Any, str]] = None,
        screenshot_np: Optional[np.ndarray] = None,
        precomputed_ocr: Optional[Tuple[str, float, float]] = None,
    ) -> Tuple[str, Optional[Any]]:
        if cache is None:
            cache = {}

        if screenshot_np is None:
            logging.error("Groq service requires a pre-captured frame for translation.")
            return "", None

        current_hash: Optional[Any] = None
        try:
            img_for_hash = Image.fromarray(screenshot_np)
            current_hash = imagehash.phash(img_for_hash)
            if current_hash == last_hash:
                return "", None
            if current_hash in cache:
                return cache[current_hash], current_hash
        except Exception as exc:
            logging.error("Failed to hash image: %s", exc)
            img_for_hash = None

        # Use precomputed OCR for logging if available (optional)
        if precomputed_ocr is not None:
            ocr_text, ocr_conf, ocr_duration_ms = precomputed_ocr
            logging.debug(
                "Using precomputed OCR: text='%s', confidence=%.2f, duration=%.1f ms",
                ocr_text,
                ocr_conf,
                ocr_duration_ms,
            )

        translation_duration_ms = 0.0

        # Image-based translation
        translate_start = time.perf_counter()
        try:
            image_b64 = encode_image_to_base64(screenshot_np)
            result = self._translate_image(image_b64, history)
        except Exception as exc:
            logging.error("Groq image translation failed: %s", exc)
            pass

        translation_duration_ms = (time.perf_counter() - translate_start) * 1000

        if result and result != "__NO_TEXT__":
            logging.info(
                "Groq Image translation completed in %.1f ms: %s",
                translation_duration_ms,
                result,
            )
            if current_hash:
                cache[current_hash] = result
                if len(cache) > self.config.max_cache_size:
                    oldest_key = next(iter(cache))
                    del cache[oldest_key]
            return result, current_hash
        else:
            logging.debug(
                "Groq Image translation returned empty in %.1f ms.",
                translation_duration_ms,
            )

        return result, current_hash

    def switch_service(self, service_name: str) -> bool:
        return service_name == "groq"

    def _handle_provider_error(self, api_key: str, exc: Exception) -> None:
        detail = str(exc).lower()
        if not detail:
            detail = exc.__class__.__name__.lower()

        auth_tokens = (
            "permission",
            "unauthorized",
            "forbidden",
            "invalid",
            "api key",
            "authentication",
        )
        if any(token in detail for token in auth_tokens):
            self._remove_key(api_key)
            return

        rate_limit_tokens = (
            "rate limit",
            "too many requests",
            "quota",
            "429",
            "slow down",
        )
        if any(token in detail for token in rate_limit_tokens):
            self._mark_key_cooldown(api_key)
        self._advance_index(api_key)
