import logging
import time
import collections
import concurrent.futures
from difflib import SequenceMatcher

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from services.translation_service_factory import TranslationServiceFactory


class TranslationWorker(QObject):
    translation_finished = pyqtSignal(str, float, object)
    translation_error = pyqtSignal(str, float)

    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self.service = None
        self.cache = {}
        self.text_cache = collections.OrderedDict()
        self.max_text_cache_size = 50
        self.duplicate_ratio = 0.92
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="Translator"
        )
        self._refresh_service()

    def _refresh_service(self):
        try:
            self.service = TranslationServiceFactory.create_service(self.config)
            logging.info(
                "Translation service initialized: %s", self.config.translation_service
            )
        except Exception as exc:
            logging.error("Failed to initialize translation service: %s", exc)
            self.service = None

    def _check_text_cache(self, ocr_text):
        if not ocr_text:
            return None
        for cached_text, cached_result in reversed(self.text_cache.items()):
            sim = SequenceMatcher(None, ocr_text, cached_text).ratio()
            if sim >= self.duplicate_ratio:
                logging.info(
                    "Text cache hit (sim=%.2f): '%s' -> '%s'",
                    sim,
                    ocr_text[:30],
                    cached_result[:30],
                )
                return cached_result
        return None

    def _add_to_text_cache(self, ocr_text, result):
        if not ocr_text or not result:
            return
        self.text_cache[ocr_text] = result
        if len(self.text_cache) > self.max_text_cache_size:
            self.text_cache.popitem(last=False)

    def _execute_translation(
        self, screenshot_np, region, precomputed_ocr, timestamp, manual=False
    ):
        if screenshot_np is None:
            self.translation_error.emit("Screenshot capture failed", timestamp)
            return

        ocr_text = precomputed_ocr[0] if precomputed_ocr else None

        # Skip text cache check in manual mode
        if not manual:
            cached_result = self._check_text_cache(ocr_text)
            if cached_result:
                self.translation_finished.emit(cached_result, timestamp, None)
                return

        if self.service is None:
            self._refresh_service()
            if self.service is None:
                self.translation_error.emit(
                    "Translation service not available", timestamp
                )
                return

        try:
            # Use empty cache in manual mode to force fresh translation
            cache_to_use = {} if manual else self.cache

            result, image_hash = self.service.get_or_translate(
                region=region,
                screenshot_np=screenshot_np,
                cache=cache_to_use,
                history=[],
                last_hash=None,
                precomputed_ocr=precomputed_ocr,
            )

            if result and result != "__NO_TEXT__":
                if ocr_text and not manual:
                    self._add_to_text_cache(ocr_text, result)
                self.translation_finished.emit(result, timestamp, image_hash)
            else:
                self.translation_error.emit(
                    "No text detected in selected area", timestamp
                )

        except Exception as exc:
            logging.error("Translation failed: %s", exc)
            self.translation_error.emit(f"Translation failed: {exc}", timestamp)

    @pyqtSlot(object, object)
    def translate_frame(
        self,
        screenshot_np,
        region,
        precomputed_ocr=None,
        manual=False,
        timestamp=None,
    ):
        if timestamp is None:
            timestamp = time.time()
        self.executor.submit(
            self._execute_translation,
            screenshot_np,
            region,
            precomputed_ocr,
            timestamp,
            manual,
        )

    def refresh_service(self):
        self._refresh_service()

    def shutdown(self):
        self.executor.shutdown(wait=False)
