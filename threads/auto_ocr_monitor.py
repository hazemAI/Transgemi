import logging
import time
import collections
from difflib import SequenceMatcher
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

from subtitle.subtitle_ocr import extract_subtitle_text


class AutoOCRMonitor(QThread):
    """Continuously OCRs a screen region and emits change_detected when text stabilizes.

    Emission logic:
    - Requires consecutive frames to be similar.
    - Similarity check must be >= sim_thresh to emit.
    - Debounced by debounce_seconds; near-duplicates (>= duplicate_ratio) are skipped.

    OCR engine is configurable via subtitle_ocr.py.
    """

    change_detected = pyqtSignal(object, object)  # (frame, (text, conf, duration_ms))

    def __init__(
        self,
        region: tuple,
        capture_func,
        source_lang: str,
        interval: float,
        sim_thresh: float,
        duplicate_ratio: float,
        debounce_seconds: float,
        stability_frames: int = 3,
    ):
        super().__init__()
        self.region = region
        self.capture_func = capture_func
        self.source_lang = source_lang.lower()
        self.interval = interval
        self.sim_thresh = sim_thresh
        self.duplicate_ratio = duplicate_ratio
        self.debounce_seconds = debounce_seconds
        self.stability_frames = max(2, min(4, stability_frames))

        logging.info(
            "AutoOCRMonitor initialized: source_lang=%s, interval=%.2fs, sim_thresh=%.2f, stability_frames=%d",
            self.source_lang,
            self.interval,
            self.sim_thresh,
            self.stability_frames,
        )

        self._running = True
        self._text_history: collections.deque = collections.deque(maxlen=4)
        self._last_emitted_text: Optional[str] = None
        self._recent_appearance = False
        self._last_change_time = time.time()
        self._last_emit_time = 0.0

    def stop(self):
        self._running = False

    def _check_stability(self):
        if len(self._text_history) < self.stability_frames:
            return False, []

        texts = list(self._text_history)[-self.stability_frames :]
        similarities = []
        for i in range(len(texts) - 1):
            sim = SequenceMatcher(None, texts[i], texts[i + 1]).ratio()
            similarities.append(sim)
            if sim < self.sim_thresh:
                return False, similarities

        return True, similarities

    def run(self):
        while self._running:
            t0 = time.time()

            frame = self.capture_func(self.region)
            if frame is None:
                time.sleep(self.interval)
                continue

            t1 = time.time()

            try:
                use_rapidocr = self.source_lang in ("zh", "chinese")
                use_winocr = not use_rapidocr
                rec_model_path = (
                    None if use_winocr else "models/ch_PP-OCRv5_rec_infer.onnx"
                )

                ocr_lang = self.source_lang

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

            if not self._running:
                break

            t2 = time.time()
            ocr_duration_ms = (t2 - t1) * 1000

            if not curr_text:
                self._text_history.append("")
                time.sleep(self.interval)
                continue

            self._text_history.append(curr_text)

            is_stable, similarities = self._check_stability()

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

            emit = False
            if is_duplicate:
                logging.debug(
                    "Skipping near-duplicate (ratio %.2f). %s",
                    dup_ratio,
                    timing_log,
                )
            elif is_stable:
                emit = True
                logging.info(
                    "Stability emission (%d-frame, sims=%s). %s",
                    self.stability_frames,
                    [f"{s:.2f}" for s in similarities],
                    timing_log,
                )
            else:
                logging.info(
                    "Chain below threshold (sims=%s). %s",
                    [f"{s:.2f}" for s in similarities] if similarities else "[]",
                    timing_log,
                )

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

            elapsed = time.time() - t0
            sleep_time = self.interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
