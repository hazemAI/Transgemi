import logging
import time
from difflib import SequenceMatcher
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

from subtitle.subtitle_ocr import extract_subtitle_text


class AutoOCRMonitor(QThread):
    """Continuously OCRs a screen region and emits change_detected when text stabilizes.

    Emission logic:
    - Requires consecutive frames to be similar (Curr ≈ Prev).
    - Similarity check must be >= sim_thresh to emit.
    - Debounced by debounce_seconds; near-duplicates (>= duplicate_ratio) are skipped.

    OCR engine is configurable via subtitle_ocr.py.
    """

    change_detected = pyqtSignal(object, object)  # (frame, (text, conf, duration_ms))

    def __init__(
        self,
        region: tuple,
        capture_func,
        lang: str,
        source_lang: str,
        interval: float,
        sim_thresh: float,
        duplicate_ratio: float,
        debounce_seconds: float,
    ):
        super().__init__()
        self.region = region
        self.capture_func = capture_func
        self.lang = lang
        self.source_lang = source_lang.lower()
        self.interval = interval
        self.sim_thresh = sim_thresh
        self.duplicate_ratio = duplicate_ratio
        self.debounce_seconds = debounce_seconds

        logging.info(
            "AutoOCRMonitor initialized: source_lang=%s, lang=%s, interval=%.2fs, sim_thresh=%.2f",
            self.source_lang,
            self.lang,
            self.interval,
            self.sim_thresh,
        )

        self._running = True
        self._prev_text: Optional[str] = None
        self._prev_prev_text: Optional[str] = None
        self._last_emitted_text: Optional[str] = None
        self._recent_appearance = False
        self._last_change_time = time.time()
        self._last_emit_time = 0.0

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            t0 = time.time()

            # Capture frame
            frame = self.capture_func(self.region)
            if frame is None:
                time.sleep(self.interval)
                continue

            t1 = time.time()

            # Perform OCR for stability check (route based on source language)
            try:
                use_rapidocr = self.source_lang in ("ja", "japanese", "zh", "chinese")
                use_winocr = not use_rapidocr
                rec_model_path = (
                    None if use_winocr else "models/ch_PP-OCRv5_rec_infer.onnx"
                )

                ocr_lang = self.source_lang if use_winocr else self.lang

                curr_text, curr_conf, engine = extract_subtitle_text(
                    frame,
                    lang=ocr_lang,
                    use_winocr=use_winocr,
                    rec_model_path=rec_model_path,
                )
                curr_text = curr_text.strip()
                logging.info(
                    "OCR Monitor [%s]: '%s' (conf=%.2f)",
                    engine,
                    curr_text[:50] if curr_text else "[empty]",
                    curr_conf,
                )
            except Exception as exc:
                logging.error("OCR Monitor failed: %s", exc)
                time.sleep(self.interval)
                continue

            # Check if we should stop after OCR (for faster response)
            if not self._running:
                break

            t2 = time.time()
            ocr_duration_ms = (t2 - t1) * 1000

            # Handle empty text
            if not curr_text:
                if self._prev_text:  # Detect disappearance
                    self._recent_appearance = False
                self._prev_prev_text = self._prev_text
                self._prev_text = curr_text
                time.sleep(self.interval)
                continue

            # Stability and duplicate checks
            emit = False
            if self._prev_text is not None:
                # Calculate similarities
                sim = SequenceMatcher(None, curr_text, self._prev_text).ratio()
                sim_prev = 0.0
                if self._prev_prev_text is not None:
                    sim_prev = SequenceMatcher(
                        None, self._prev_text, self._prev_prev_text
                    ).ratio()

                # Detect new appearance
                if not self._prev_text and curr_text:
                    self._recent_appearance = True
                    self._last_change_time = time.time()

                # Check for duplicates
                is_duplicate = False
                if self._last_emitted_text:
                    dup_ratio = SequenceMatcher(
                        None, curr_text, self._last_emitted_text
                    ).ratio()
                    if dup_ratio >= self.duplicate_ratio:
                        is_duplicate = True

                t3 = time.time()

                time_since_change = time.time() - self._last_change_time
                timing_log = (
                    f"Timings(ms): Capture={int((t1 - t0) * 1000)}, "
                    f"OCR={int(ocr_duration_ms)}, Logic={int((t3 - t2) * 1000)}. "
                    f"Since change: {time_since_change:.2f}s"
                )

                if is_duplicate:
                    logging.debug(
                        "Skipping near-duplicate (ratio %.2f). %s",
                        dup_ratio,
                        timing_log,
                    )
                else:
                    # 2-frame stability check (curr matches prev)
                    if sim >= self.sim_thresh:
                        emit = True
                        logging.info("Stability emission (2-frame). %s", timing_log)
                        self._recent_appearance = False

                if not emit and not is_duplicate:
                    logging.info(
                        "Chain below threshold (sim=%.2f, sim_prev=%.2f). %s",
                        sim,
                        sim_prev,
                        timing_log,
                    )

            # Emit signal if stable and debounced
            if emit:
                now = time.time()
                if now - self._last_emit_time < self.debounce_seconds:
                    logging.debug("Debounce: Too soon after last emit; skipping.")
                else:
                    ocr_data = (curr_text, curr_conf, ocr_duration_ms)
                    self.change_detected.emit(frame, ocr_data)
                    self._last_emitted_text = curr_text
                    self._last_emit_time = now
                    self._last_change_time = now

            # Update history
            self._prev_prev_text = self._prev_text
            self._prev_text = curr_text

            # Sleep to maintain interval
            elapsed = time.time() - t0
            sleep_time = self.interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
