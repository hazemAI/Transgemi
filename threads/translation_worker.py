import logging
import time

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from services.translation_service_factory import TranslationServiceFactory


class TranslationWorker(QObject):
    """Worker for background translation.

    Runs one translation at a time in a dedicated QThread.
    Used by both manual and auto translation modes.
    """

    # Signals
    translation_finished = pyqtSignal(
        str, float, object
    )  # (translation_text, timestamp, image_hash)
    translation_error = pyqtSignal(str)  # (error_message)

    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self.service = None
        self.cache = {}  # Translation cache
        self._refresh_service()

    def _refresh_service(self):
        """Refresh translation service from config."""
        try:
            self.service = TranslationServiceFactory.create_service(self.config)
            logging.info(
                "Translation service initialized: %s", self.config.translation_service
            )
        except Exception as exc:
            logging.error("Failed to initialize translation service: %s", exc)
            self.service = None

    @pyqtSlot(object, object)
    def translate_frame(self, screenshot_np, region, precomputed_ocr=None):
        """Translate a captured frame (manual mode).

        Args:
            screenshot_np: Screenshot as numpy array
            region: Screen region tuple (x, y, width, height)
            precomputed_ocr: Optional tuple (text, conf, duration_ms) from auto monitor
        """
        if screenshot_np is None:
            self.translation_error.emit("Screenshot capture failed")
            return

        if self.service is None:
            self._refresh_service()
            if self.service is None:
                self.translation_error.emit("Translation service not available")
                return

        try:
            timestamp = time.time()

            # Perform translation (OCR + translation handled by service)
            result, image_hash = self.service.get_or_translate(
                region=region,
                screenshot_np=screenshot_np,
                cache=self.cache,  # Use instance cache
                history=[],  # No history for manual mode
                last_hash=None,
                precomputed_ocr=precomputed_ocr,
            )

            if result and result != "__NO_TEXT__":
                self.translation_finished.emit(result, timestamp, image_hash)
            else:
                self.translation_error.emit("No text detected in selected area")

        except Exception as exc:
            logging.error("Translation failed: %s", exc)
            self.translation_error.emit(f"Translation failed: {exc}")

    def refresh_service(self):
        """Public method to refresh service (e.g., when user changes service)."""
        self._refresh_service()
