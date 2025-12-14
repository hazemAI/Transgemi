import logging
import os
import threading
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


class ConfigManager:
    def __init__(self, env_file: str = ".env"):
        # Go up one level from core/ to project root
        env_path = Path(__file__).resolve().parent.parent / env_file
        self._env_path = env_path
        load_dotenv(env_path)
        self._write_lock = threading.Lock()
        self._translation_service = os.getenv("TRANSLATION_SERVICE", "gemini")
        self._gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self._gemini_model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
        self._openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self._openrouter_model = os.getenv("OPENROUTER_MODEL", "")
        self._openrouter_base_url = os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )
        self._groq_api_key = os.getenv("GROQ_API_KEY", "")
        self._groq_model = os.getenv(
            "GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
        )
        self._groq_base_url = os.getenv(
            "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
        )
        self._sambanova_api_key = os.getenv("SAMBANOVA_API_KEY", "")
        self._sambanova_model = os.getenv(
            "SAMBANOVA_MODEL", "Llama-4-Maverick-17B-128E-Instruct"
        )
        self._sambanova_base_url = os.getenv(
            "SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1"
        )
        self._cerebras_api_key = os.getenv("CEREBRAS_API_KEY", "")
        self._cerebras_model = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b")
        self._cerebras_base_url = os.getenv(
            "CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1"
        )
        self._temperature = float(os.getenv("TEMPERATURE", "0.1"))
        self._max_tokens = int(os.getenv("MAX_TOKENS", "1024"))
        self._top_p = float(os.getenv("TOP_P", "0.1"))
        self._frequency_penalty = float(os.getenv("FREQUENCY_PENALTY", "0.0"))
        self._presence_penalty = float(os.getenv("PRESENCE_PENALTY", "0.0"))

        auto_translation_raw = (
            os.getenv("AUTO_TRANSLATION_ENABLED", "0").strip().lower()
        )
        self._auto_translation_enabled = auto_translation_raw not in {
            "0",
            "false",
            "no",
        }

        self._status_clear_ms = int(os.getenv("STATUS_CLEAR_MS", "5000"))
        self._duplicate_ratio = float(os.getenv("DUPLICATE_RATIO", "0.95"))
        self._max_cache_size = int(os.getenv("MAX_CACHE_SIZE", "100"))
        self._cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "60"))
        self._auto_max_backlog = int(os.getenv("AUTO_MAX_BACKLOG", "0"))

        self._subtitle_ocr_min_confidence = float(
            os.getenv("SUBTITLE_OCR_MIN_CONFIDENCE", "0.55")
        )
        self._subtitle_ocr_max_lines = int(os.getenv("SUBTITLE_OCR_MAX_LINES", "1"))
        disable_reasoning_raw = os.getenv("OPENROUTER_DISABLE_REASONING_MODELS", "")
        self._openrouter_disable_reasoning_models = tuple(
            item.strip().lower()
            for item in disable_reasoning_raw.split(",")
            if item.strip()
        )
        self._font_size = int(os.getenv("FONT_SIZE", "22"))
        self._overlay_width = int(os.getenv("OVERLAY_WIDTH", "300"))
        self._overlay_height = int(os.getenv("OVERLAY_HEIGHT", "700"))

        # OCR Monitor Thread (Defaults handled in AutoOCRMonitor)
        self._ocr_monitor_interval = float(os.getenv("OCR_MONITOR_INTERVAL", "0.15"))
        self._ocr_similarity_threshold = float(
            os.getenv("OCR_SIMILARITY_THRESHOLD", "0.85")
        )
        self._ocr_duplicate_ratio = float(os.getenv("OCR_DUPLICATE_RATIO", "0.95"))
        self._ocr_debounce_seconds = float(os.getenv("OCR_DEBOUNCE_SECONDS", "0.2"))
        self._ocr_stability_frames = int(os.getenv("OCR_STABILITY_FRAMES", "3"))

        self._source_language = os.getenv("SOURCE_LANGUAGE", "ja").lower()
        self._target_language = os.getenv("TARGET_LANGUAGE", "en").lower()

    def _get_optional_float(self, key: str) -> Optional[float]:
        val = os.getenv(key)
        if val is not None:
            try:
                return float(val)
            except ValueError:
                return None
        return None

    @property
    def translation_service(self) -> str:
        return self._translation_service

    @translation_service.setter
    def translation_service(self, value: str) -> None:
        self._translation_service = value
        logging.info(f"Translation service changed to: {value}")
        self._write_env_value("TRANSLATION_SERVICE", value)

    def _write_env_value(self, key: str, value: str) -> None:
        try:
            with self._write_lock:
                lines: List[str] = []
                if self._env_path.exists():
                    lines = self._env_path.read_text(encoding="utf-8").splitlines()

                key_prefix = f"{key}="
                replaced = False
                for index, line in enumerate(lines):
                    if line.strip().startswith(key_prefix):
                        lines[index] = f"{key}={value}"
                        replaced = True
                        break

                if not replaced:
                    lines.append(f"{key}={value}")

                new_content = "\n".join(lines)
                if lines and not new_content.endswith("\n"):
                    new_content += "\n"

                self._env_path.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            logging.error("Failed to persist %s to %s: %s", key, self._env_path, exc)

    @property
    def gemini_api_key(self) -> str:
        return self._gemini_api_key

    @gemini_api_key.setter
    def gemini_api_key(self, value: str) -> None:
        self._gemini_api_key = value.strip()
        self._write_env_value("GEMINI_API_KEY", self._gemini_api_key)
        logging.info("Gemini API key updated and saved.")

    @property
    def gemini_model(self) -> str:
        return self._gemini_model

    @property
    def openrouter_api_key(self) -> str:
        return self._openrouter_api_key

    @openrouter_api_key.setter
    def openrouter_api_key(self, value: str) -> None:
        self._openrouter_api_key = value.strip()
        self._write_env_value("OPENROUTER_API_KEY", self._openrouter_api_key)
        logging.info("OpenRouter API key updated and saved.")

    @property
    def openrouter_model(self) -> str:
        return self._openrouter_model

    @property
    def openrouter_base_url(self) -> str:
        return self._openrouter_base_url

    @property
    def groq_api_key(self) -> str:
        return self._groq_api_key

    @property
    def openrouter_disable_reasoning_models(self) -> tuple:
        return self._openrouter_disable_reasoning_models

    @groq_api_key.setter
    def groq_api_key(self, value: str) -> None:
        self._groq_api_key = value.strip()
        self._write_env_value("GROQ_API_KEY", self._groq_api_key)
        logging.info("Groq API key updated and saved.")

    @property
    def groq_model(self) -> str:
        return self._groq_model

    @property
    def groq_base_url(self) -> str:
        return self._groq_base_url

    @property
    def sambanova_api_key(self) -> str:
        return self._sambanova_api_key

    @sambanova_api_key.setter
    def sambanova_api_key(self, value: str) -> None:
        self._sambanova_api_key = value.strip()
        self._write_env_value("SAMBANOVA_API_KEY", self._sambanova_api_key)
        logging.info("SambaNova API key updated and saved.")

    @property
    def sambanova_model(self) -> str:
        return self._sambanova_model

    @property
    def sambanova_base_url(self) -> str:
        return self._sambanova_base_url

    @property
    def cerebras_api_key(self) -> str:
        return self._cerebras_api_key

    @cerebras_api_key.setter
    def cerebras_api_key(self, value: str) -> None:
        self._cerebras_api_key = value.strip()
        self._write_env_value("CEREBRAS_API_KEY", self._cerebras_api_key)
        logging.info("Cerebras API key updated and saved.")

    @property
    def cerebras_model(self) -> str:
        return self._cerebras_model

    @property
    def cerebras_base_url(self) -> str:
        return self._cerebras_base_url

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def top_p(self) -> float:
        return self._top_p

    @property
    def frequency_penalty(self) -> float:
        return self._frequency_penalty

    @property
    def presence_penalty(self) -> float:
        return self._presence_penalty

    @property
    def auto_translation_enabled(self) -> bool:
        return self._auto_translation_enabled

    @auto_translation_enabled.setter
    def auto_translation_enabled(self, value: bool) -> None:
        self._auto_translation_enabled = value
        self._write_env_value("AUTO_TRANSLATION_ENABLED", "1" if value else "0")

    @property
    def status_clear_ms(self) -> int:
        return self._status_clear_ms

    @property
    def duplicate_ratio(self) -> float:
        return self._duplicate_ratio

    @property
    def max_cache_size(self) -> int:
        return self._max_cache_size

    @property
    def cooldown_seconds(self) -> int:
        return self._cooldown_seconds

    @property
    def auto_max_backlog(self) -> int:
        return self._auto_max_backlog

    @auto_max_backlog.setter
    def auto_max_backlog(self, value: int) -> None:
        self._auto_max_backlog = max(0, int(value))
        self._write_env_value("AUTO_MAX_BACKLOG", str(self._auto_max_backlog))

    @property
    def subtitle_ocr_min_confidence(self) -> float:
        return self._subtitle_ocr_min_confidence

    @property
    def subtitle_ocr_max_lines(self) -> int:
        return self._subtitle_ocr_max_lines

    @property
    def font_size(self) -> int:
        return self._font_size

    @font_size.setter
    def font_size(self, value: int) -> None:
        self._font_size = value
        self._write_env_value("FONT_SIZE", str(value))

    @property
    def overlay_width(self) -> int:
        return self._overlay_width

    @overlay_width.setter
    def overlay_width(self, value: int) -> None:
        self._overlay_width = value
        self._write_env_value("OVERLAY_WIDTH", str(value))

    @property
    def overlay_height(self) -> int:
        return self._overlay_height

    @overlay_height.setter
    def overlay_height(self, value: int) -> None:
        self._overlay_height = value
        self._write_env_value("OVERLAY_HEIGHT", str(value))

    @property
    def ocr_monitor_interval(self) -> float:
        return self._ocr_monitor_interval

    @property
    def ocr_similarity_threshold(self) -> float:
        return self._ocr_similarity_threshold

    @property
    def ocr_duplicate_ratio(self) -> float:
        return self._ocr_duplicate_ratio

    @property
    def ocr_debounce_seconds(self) -> float:
        return self._ocr_debounce_seconds

    @property
    def ocr_stability_frames(self) -> int:
        return max(2, min(4, self._ocr_stability_frames))

    @property
    def source_language(self) -> str:
        return self._source_language

    @source_language.setter
    def source_language(self, value: str) -> None:
        self._source_language = value.lower()
        self._write_env_value("SOURCE_LANGUAGE", self._source_language)
        logging.info("Source language changed to: %s", self._source_language)

    @property
    def target_language(self) -> str:
        return self._target_language

    @target_language.setter
    def target_language(self, value: str) -> None:
        self._target_language = value.lower()
        self._write_env_value("TARGET_LANGUAGE", self._target_language)
        logging.info("Target language changed to: %s", self._target_language)
