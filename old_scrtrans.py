from PIL import Image
import pyautogui
import numpy as np
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QTextEdit,
    QSizeGrip,
    QShortcut,
    QLabel,
    QInputDialog,
    QLineEdit,
    QDialog,
    QRubberBand,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QObject, pyqtSlot, QTimer, QRect
from PyQt5.QtGui import QTextCursor, QKeySequence, QGuiApplication, QCursor
import logging
import time
from google import genai
from google.genai import types
import ctypes
from ctypes import wintypes
import tempfile
import os
import re
from difflib import SequenceMatcher
import collections
import imagehash
from winocr import recognize_cv2_sync
import concurrent.futures


user32 = ctypes.windll.user32
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
MOD_ALT = 0x0001

VK_OEM_3 = 0xC0
VK_T = 0x54
VK_Q = 0x51
VK_K = 0x4B
VK_L = 0x4C
ALT_T_HOTKEY_ID = 1
ALT_Q_HOTKEY_ID = 2
TILDE_HOTKEY_ID = 3
ALT_K_HOTKEY_ID = 6
ALT_L_HOTKEY_ID = 7

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

API_KEY = "AIzaSyBYTMvbd7BPp-sK5XpNsn2Po2Ung8rKHX4"


TRANSLATION_CACHE = collections.OrderedDict()
MAX_CACHE_SIZE = 100
MODEL_COOLDOWNS = {}
COOLDOWN_SECONDS = 60


STATUS_CLEAR_MS = 5000
EMIT_DEBOUNCE_SECONDS = 0.2
OCR_INTERVAL_DEFAULT = 0.15
OCR_SIM_THRESH_DEFAULT = 0.85
DUPLICATE_RATIO = 0.95

_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-1.5-flash-8b",
    "learnlm-2.0-flash-experimental",
]


class RegionSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        screens = QGuiApplication.screens() or [QGuiApplication.primaryScreen()]
        left = min(s.geometry().left() for s in screens)
        top = min(s.geometry().top() for s in screens)
        right = max(s.geometry().right() for s in screens)
        bottom = max(s.geometry().bottom() for s in screens)
        self.setGeometry(QRect(left, top, right - left + 1, bottom - top + 1))

        self.origin_global = None
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self._selected = None

    def showEvent(self, event):
        super().showEvent(event)

        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)
        try:
            user32.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass

        QTimer.singleShot(0, self._grab_inputs)

    def _grab_inputs(self):
        try:
            if self.isVisible():
                self.grabKeyboard()
                self.grabMouse(Qt.CrossCursor)
        except Exception:
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._selected = None
            self.reject()
            return
        if event.button() == Qt.LeftButton:
            self.origin_global = event.globalPos()
            start_local = self.mapFromGlobal(self.origin_global)
            self.rubber_band.setGeometry(QRect(start_local, start_local))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if self.origin_global is not None:
            start_local = self.mapFromGlobal(self.origin_global)
            now_local = self.mapFromGlobal(event.globalPos())
            self.rubber_band.setGeometry(QRect(start_local, now_local).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.origin_global is not None:
            rect = self.rubber_band.geometry()
            top_left = self.mapToGlobal(rect.topLeft())
            self._selected = (top_left.x(), top_left.y(), rect.width(), rect.height())
            self.accept()

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_X) and (event.modifiers() & Qt.AltModifier):
            self._selected = None
            self.reject()
            event.accept()
            return

        if event.key() == Qt.Key_Escape:
            event.accept()
            return
        else:
            super().keyPressEvent(event)

    def get_selection(self):
        return self._selected

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QColor

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

    def closeEvent(self, event):
        try:
            self.releaseKeyboard()
            self.releaseMouse()
        except Exception:
            pass
        super().closeEvent(event)


def select_screen_region_with_mouse(parent=None):
    print("Please select a part of the screen using the mouse.")
    dlg = RegionSelector(parent)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    QApplication.setActiveWindow(dlg)
    if dlg.exec_() == QDialog.Accepted:
        sel = dlg.get_selection()
        if sel and sel[2] > 0 and sel[3] > 0:
            x, y, w, h = sel
            print(f"Selected region: (X: {x}, Y: {y}, Width: {w}, Height: {h})")
            return (x, y, w, h)
    print("Selection cancelled.")
    return None


def capture_screen_region(region):
    if not region or region[2] <= 0 or region[3] <= 0:
        logging.warning(f"Invalid screen region provided: {region}. Skipping capture.")
        return None
    try:
        print(f"Capturing screen region: {region}...")
        screenshot = pyautogui.screenshot(region=region)
        return np.array(screenshot)
    except Exception as e:
        print(f"Error capturing screen region: {e}")
        return None


def gemini_translate_image_request(image_path, from_lang, to_lang, history=None):
    """Translate text in an image using Gemini models (tries multiple models sequentially).

    Args:
        image_path (str): Path to a PNG of the selected region.
        from_lang (str): Source language ('auto' to let the model infer).
        to_lang (str): Target language (e.g., 'arabic').
        history (list[str] | None): Recent translations to preserve context/consistency.

    Returns:
        str: Pure translated text, or '__NO_TEXT__' when no readable text is found,
             or an error string like 'Translation failed: All models unavailable'.

    Notes:
        - Applies per-model cooldown on HTTP 429 responses.
        - Skips English-only outputs when the target is not English.
        - Honors a minimal token budget on '2.5' models via thinking_config.
    """
    if not API_KEY:
        logging.error(
            "Gemini API key missing. Set GEMINI_API_KEY or use Alt+K to set it at runtime."
        )
        return "Error: Missing API key"
    try:
        img = Image.open(image_path)
    except Exception as e:
        logging.error(f"Failed to open image for translation: {e}")
        return "Error: Cannot open image"

    if from_lang.lower() in ("", "auto", "any"):
        prompt_header = (
            "SYSTEM:\n"
            "You are a high-accuracy multilingual translator. An IMAGE containing some text will be provided. "
            f"Translate EVERY piece of text you can read into {to_lang.upper()} ONLY. "
            f"Even if text appears to be in English, translate it fully to {to_lang.upper()}, including titles, journey names, nicknames, or quoted phrases. "
            "Only leave unchanged if it is an untranslatable proper noun like a real-world brand name; otherwise, provide a natural translation. "
            "Specifically, translate the content inside any quotes or subtitles, as leaving English unchanged provides no value if it is already visible."
        )
    else:
        prompt_header = (
            "SYSTEM:\n"
            f"You are a high-accuracy translator. An IMAGE containing text written in {from_lang.upper()} will be provided. "
            f"Translate it into {to_lang.upper()} ONLY. "
            "Leave unchanged any untranslatable proper nouns (e.g., brand names)."
        )
    context_prompt = ""
    if history:
        context_lines = [
            "\n\nCONTEXT: These are the most recent translations. Use them to maintain conversational flow and consistency:",
        ]
        context_lines.extend(f"- {item}" for item in history)
        context_prompt = "\n".join(context_lines)
    prompt_footer = (
        "\n\nGuidelines:\n"
        "1. If some text is ALREADY in the target language, keep it as is.\n"
        "2. If the image has NO readable text, you MUST output the exact token `__NO_TEXT__` and nothing else.\n"
        "3. Output **pure translated text** – no comments, no language tags, no explanations.\n"
        "4. DO NOT return English words unless they are part of proper names and must remain unchanged.\n"
        "5. Never output phrases like 'No text in the image' nor any apology."
    )
    prompt = prompt_header + context_prompt + prompt_footer
    _SAFETY_OFF = [
        types.SafetySetting(category=cat, threshold=types.HarmBlockThreshold.BLOCK_NONE)
        for cat in (
            types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
        )
    ]
    client = genai.Client(api_key=API_KEY)
    for model_name in _MODELS:
        if model_name in MODEL_COOLDOWNS and time.time() < MODEL_COOLDOWNS[model_name]:
            logging.info(f"Model {model_name} is on cooldown. Skipping.")
            continue
        logging.info(f"Attempting translation with model: {model_name}")
        try:
            cfg_kwargs = {"max_output_tokens": 96, "temperature": 0.0}
            if "2.5" in model_name:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            gen_config = types.GenerateContentConfig(
                **cfg_kwargs, safety_settings=_SAFETY_OFF
            )
            contents = [prompt, img]
            response = client.models.generate_content(
                model=model_name, contents=contents, config=gen_config
            )
            result = (response.text or "").strip()
            if not result or result in (
                "No text in the image",
                "No text in the image.",
            ):
                logging.info(
                    f"Model {model_name} found no text or returned empty. Trying next model."
                )
                continue

            if to_lang.lower() not in ("english", "en") and re.fullmatch(
                r'^[A-Za-z0-9\s\.,!\?\:;\'"()\-]+$', result
            ):
                logging.info(
                    f"English-only output from {model_name} while target is {to_lang}; trying next model."
                )
                continue
            logging.info(f"Successful translation from {model_name}.")
            if result:
                return result
        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                logging.warning(
                    f"Rate limit hit for model {model_name}. Placing on cooldown for {COOLDOWN_SECONDS}s."
                )
                MODEL_COOLDOWNS[model_name] = time.time() + COOLDOWN_SECONDS
            else:
                logging.error(f"Translation failed with model {model_name}: {e}")
            continue
    logging.error("All models failed or are on cooldown. No translation available.")
    return "Translation failed: All models unavailable"


class DraggableTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent

    def mousePressEvent(self, event):
        if self.parent_widget:
            self.parent_widget.mousePressEvent(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.parent_widget:
            self.parent_widget.mouseMoveEvent(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.parent_widget:
            self.parent_widget.mouseReleaseEvent(event)
        super().mouseReleaseEvent(event)


class TranslatorApp(QMainWindow):
    """Topmost, draggable overlay that displays live translations.

    Responsibilities:
    - Manages UI, hotkeys, and selection of a screen region.
    - Emits translate_requested(region, src, tgt, history, last_hash) to the worker.
    - Maintains translation history and deduplicates similar outputs.
    - Applies a simple per-call cooldown to avoid excessive API usage.
    """

    translate_requested = pyqtSignal(tuple, str, str, list, object)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)

        self.setFocusPolicy(Qt.ClickFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)

        screen_geometry = QApplication.primaryScreen().availableGeometry()
        width = 180
        height = 500
        self.setGeometry(
            screen_geometry.left(), screen_geometry.bottom() - height, width, height
        )

        self.selected_region = None
        self.font_sizes = [
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            18,
            20,
            22,
            24,
            26,
            28,
            36,
            48,
            72,
        ]
        self.font_size_index = self.font_sizes.index(15)

        self.live_translation = False

        self.source_lang = "auto"
        self.target_lang = "arabic"

        self.selecting = False

        self.last_translation_time = 0.0

        self.translation_cooldown = 1.0
        self.last_translation_result = None
        self.last_update_timestamp = 0.0

        self.translation_history = collections.deque(maxlen=3)
        self.last_processed_hash = None

        self.monitor_thread = None
        self.worker_thread = None
        self.worker = None

        self.status_label = None
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.clear_status)

        self.placeholder_text = (
            "Transgemi\n\n"
            "Press 'Alt+Q' to select an area to translate and 'Alt+X' to cancel selection\n\n"
            "Press '~' to live translate the selected area\n\n"
            "Press 'Alt+K' to set your Gemini API key\n\n"
            "Press 'Alt+L' to set languages (src > tgt)\n\n"
            "Press '+' or '-' to change font size\n\n"
            "Press 'Alt+T' to show or hide the translation window\n\n"
            "Press 'Esc' to close"
        )

        self.init_ui()
        self.setup_hotkeys()
        self.show_placeholder()

        self.alt_t_hotkey_id = ALT_T_HOTKEY_ID

        hwnd = int(self.winId())
        self.hwnd = hwnd

        try:
            orig_style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
            new_style = (orig_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, new_style)
        except Exception:
            pass
        if not user32.RegisterHotKey(
            hwnd, self.alt_t_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_T
        ):
            logging.error("Failed to register global hotkey Alt+T")

        self.alt_q_hotkey_id = ALT_Q_HOTKEY_ID
        if not user32.RegisterHotKey(
            hwnd, self.alt_q_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_Q
        ):
            logging.error("Failed to register global hotkey Alt+Q")

        self.tilde_hotkey_id = TILDE_HOTKEY_ID
        if not user32.RegisterHotKey(
            hwnd, self.tilde_hotkey_id, 0 | MOD_NOREPEAT, VK_OEM_3
        ):
            logging.error("Failed to register global hotkey '~'")

        self.alt_k_hotkey_id = ALT_K_HOTKEY_ID
        if not user32.RegisterHotKey(
            hwnd, self.alt_k_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_K
        ):
            logging.error("Failed to register global hotkey Alt+K")

        self.alt_l_hotkey_id = ALT_L_HOTKEY_ID
        if not user32.RegisterHotKey(
            hwnd, self.alt_l_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_L
        ):
            logging.error("Failed to register global hotkey Alt+L")

        self.worker_thread = QThread(self)
        self.worker = TranslationWorker()
        self.worker.moveToThread(self.worker_thread)
        self.worker.finished.connect(self.on_translation_finished)
        self.worker_thread.start()

        self.translate_requested.connect(self.worker.translate)

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.text_edit = DraggableTextEdit(self)
        self.text_edit.setReadOnly(True)

        self.update_font_size()

        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(self.text_edit, 1)

        self.status_indicator = QWidget(self.text_edit)
        self.status_indicator.setFixedSize(12, 12)
        self.status_indicator.move(5, 5)
        self.status_indicator.setStyleSheet(
            "background-color: red; border-radius: 6px;"
        )
        self.status_indicator.show()

        self.sizegrip = QSizeGrip(self.text_edit)

        self.status_label = QLabel(self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: black;
                color: #ADD8E6;
                font-style: italic;
                padding: 4px;
                font-size: 9pt;
            }
        """)
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)
        self.status_label.hide()

    def update_font_size(self):
        font_size = self.font_sizes[self.font_size_index]
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: black;
                color: white;
                border: none;
                font-family: "Segoe UI", "Traditional Arabic", Tahoma, Arial, sans-serif;
                font-size: {font_size}px;
                padding-top: 20px;
                padding-left: 0px;
                padding-right: 0px;
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: 8px;
                margin: 0 2px 0 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: #444;
                border-radius: 4px;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                background: none;
                height: 0;
            }}
            QScrollBar::add-page, QScrollBar::sub-page {{
                background: none;
            }}
        """)

    def position_grip(self):
        text_rect = self.text_edit.contentsRect()
        self.sizegrip.move(
            text_rect.right() - self.sizegrip.width(),
            text_rect.bottom() - self.sizegrip.height(),
        )
        self.sizegrip.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_grip()

    def showEvent(self, event):
        super().showEvent(event)

        self.position_grip()

        try:
            user32.SetWindowPos(
                self.hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE,
            )
        except Exception:
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if hasattr(self, "drag_offset") and self.drag_offset:
            self.move(event.globalPos() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None

    def _get_text_dialog(self, title, label, default_text="", password=False):
        dlg = QInputDialog(self, flags=Qt.Dialog | Qt.WindowStaysOnTopHint)
        dlg.setModal(True)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setLabelText(label)
        dlg.setTextValue(default_text)
        if password:
            dlg.setTextEchoMode(QLineEdit.Password)

        try:
            screen = (
                QGuiApplication.screenAt(QCursor.pos())
                or QGuiApplication.primaryScreen()
            )
            geo = screen.availableGeometry()
        except Exception:
            geo = QApplication.primaryScreen().availableGeometry()
        dlg.adjustSize()
        rect = dlg.frameGeometry()
        rect.moveCenter(geo.center())
        dlg.move(rect.topLeft())
        dlg.show()
        QApplication.processEvents()
        dlg.raise_()
        dlg.activateWindow()
        QApplication.setActiveWindow(dlg)
        if dlg.exec_() and dlg.textValue():
            return dlg.textValue()
        return None

    def set_api_key(self):
        global API_KEY

        self.hide()
        new_key = self._get_text_dialog(
            "API Key", "Enter your Google Gemini API Key:", "", password=True
        )
        self.show()

        self.show_placeholder()
        if new_key:
            API_KEY = new_key.strip()
            logging.info("API Key updated.")
            self.append_status("API Key updated successfully.")
        else:
            logging.info("API Key update cancelled.")
            self.append_status("API Key update cancelled.")

    def set_target_language(self):
        """Ask the user for languages in the form 'src > tgt' (e.g., 'auto > arabic').
        The left side may be 'auto' or blank to let Gemini auto-detect."""

        self.hide()
        default_value = f"{self.source_lang or 'auto'} > {self.target_lang}"
        prompt = "Enter languages in the form 'source > target': \n(Note: Source OCR currently supports Latin-script languages only.)"
        input_str = self._get_text_dialog("Languages", prompt, default_value)
        self.show()

        self.show_placeholder()
        if not input_str:
            logging.info("Language update cancelled.")
            self.append_status("Language update cancelled.")
            return

        parts = [p.strip().lower() for p in re.split(r">", input_str, maxsplit=1)]
        if len(parts) != 2 or not parts[1]:
            logging.warning("Invalid language format entered.")
            self.append_status("Invalid format. Use 'src > tgt'.")
            return

        self.source_lang = parts[0] or "auto"
        self.target_lang = parts[1]
        self.append_status(
            f"Languages set: {self.source_lang.upper()} ➜ {self.target_lang.upper()}"
        )
        logging.info(f"Languages updated to {self.source_lang} -> {self.target_lang}")

    def select_area(self):
        if self.selecting:
            return
        self.selecting = True

        if self.live_translation:
            self.toggle_live_translation()

        try:
            user32.UnregisterHotKey(self.hwnd, self.tilde_hotkey_id)
        except Exception:
            pass

        try:
            self.selected_region = select_screen_region_with_mouse(self)
            if self.selected_region:
                print(f"Selected region: {self.selected_region}")

                self.toggle_live_translation()
        finally:
            try:
                user32.RegisterHotKey(
                    self.hwnd, self.tilde_hotkey_id, 0 | MOD_NOREPEAT, VK_OEM_3
                )
            except Exception:
                pass

            self.selecting = False

    def start_translation(self):
        if not self.selected_region:
            self.text_edit.setAlignment(Qt.AlignCenter)
            self.text_edit.setText("Please select an area first.")
            return

        if self.text_edit.toPlainText() in (
            self.placeholder_text,
            "Please select an area first.",
        ):
            self.text_edit.clear()

        self.translate_requested.emit(
            self.selected_region,
            self.source_lang,
            self.target_lang,
            list(self.translation_history),
            self.last_processed_hash,
        )

    def on_translation_finished(self, result, processed_hash, timestamp):
        if timestamp < self.last_update_timestamp:
            logging.info("Skipping stale translation.")
            return

        self.last_update_timestamp = timestamp

        self.last_processed_hash = processed_hash

        normalized = result.strip()
        if not normalized or normalized == "__NO_TEXT__":
            logging.info("No significant text found, skipping UI update.")
            return

        if self.last_translation_result:
            similarity = SequenceMatcher(
                None, normalized, self.last_translation_result
            ).ratio()

            if similarity >= 0.85 and len(normalized) <= len(
                self.last_translation_result
            ):
                logging.info(
                    f"Skipping update – similarity {similarity:.2f} and no additional content."
                )
                return

        self.translation_history.append(normalized)
        self.last_translation_result = normalized

        if self.text_edit.toPlainText():
            self.text_edit.append("")

            self.text_edit.setLayoutDirection(Qt.RightToLeft)
            self.text_edit.setAlignment(Qt.AlignRight)

        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_edit.setTextCursor(cursor)

        lines = result.split("\\n")
        p_style = 'dir="rtl" style="margin: 0; padding: 0; line-height: 120%; text-align: right;"'

        html_lines = [f"<p {p_style}>{line or '&nbsp;'}</p>" for line in lines]
        html_result = "".join(html_lines)

        self.text_edit.insertHtml(html_result)

        self.text_edit.append("")

        self.text_edit.verticalScrollBar().setValue(
            self.text_edit.verticalScrollBar().maximum()
        )
        QApplication.processEvents()

    def show_placeholder(self):
        self.text_edit.clear()
        self.text_edit.setText(self.placeholder_text)
        self.text_edit.setAlignment(Qt.AlignCenter)
        self.clear_status()

    def increase_font(self):
        if self.font_size_index < len(self.font_sizes) - 1:
            self.font_size_index += 1
            self.update_font_size()

    def decrease_font(self):
        if self.font_size_index > 0:
            self.font_size_index -= 1
            self.update_font_size()

    def setup_hotkeys(self):
        self.shortcut_inc1 = QShortcut(QKeySequence("+"), self)
        self.shortcut_inc1.activated.connect(self.increase_font)
        self.shortcut_inc2 = QShortcut(QKeySequence("="), self)
        self.shortcut_inc2.activated.connect(self.increase_font)

        self.shortcut_dec = QShortcut(QKeySequence("-"), self)
        self.shortcut_dec.activated.connect(self.decrease_font)

        self.shortcut_close = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_close.setContext(Qt.WindowShortcut)
        self.shortcut_close.activated.connect(self.close)

    def closeEvent(self, event):
        print("Closing application...")

        try:
            user32.UnregisterHotKey(self.hwnd, self.alt_t_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, self.alt_q_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, self.tilde_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, self.alt_k_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, self.alt_l_hotkey_id)
        except Exception:
            pass

        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            self.monitor_thread.wait()

        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

        if self.worker:
            self.worker.shutdown()

        QApplication.quit()
        event.accept()

    def toggle_live_translation(self):
        self.live_translation = not self.live_translation
        if self.live_translation:
            if not self.selected_region:
                logging.warning("Cannot start live translation: No region selected.")
                self.live_translation = False
                self.append_status("Cannot start: Select a region with Alt+Q first.")
                return

            self.text_edit.clear()
            self.append_status("Live Translation Started")

            self.perform_live_translation()

            self.monitor_thread = WinOCRMonitorThread(self.selected_region, lang="en")
            self.monitor_thread.change_detected.connect(self.perform_live_translation)
            self.monitor_thread.start()

            self.last_translation_result = None
        else:
            if self.monitor_thread:
                self.monitor_thread.stop()
                self.monitor_thread.wait()
                self.monitor_thread = None
            self.append_status("Live Translation Stopped")

        color = "#0f0" if self.live_translation else "#f00"
        radius = self.status_indicator.width() // 2
        self.status_indicator.setStyleSheet(
            f"background-color: {color}; border-radius: {radius}px;"
        )

    def clear_status(self):
        self.status_label.setText("")
        self.status_label.hide()

    def append_status(self, text):
        self.status_label.setText(text)
        self.status_label.show()
        self.status_timer.start(STATUS_CLEAR_MS)

    def perform_live_translation(self):
        """Slot for the monitor thread. Triggers a translation."""

        if not self.live_translation or not self.selected_region:
            return
        now = time.time()
        if (
            self.last_translation_time
            and (now - self.last_translation_time) < self.translation_cooldown
        ):
            return

        self.last_translation_time = now
        self.start_translation()

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                if hotkey_id == self.alt_t_hotkey_id:
                    if self.isVisible():
                        self.hide()
                    else:
                        self.show()
                    return True, 0
                elif hotkey_id == self.alt_q_hotkey_id:
                    self.select_area()
                    return True, 0
                elif hotkey_id == self.tilde_hotkey_id:
                    if self.selecting:
                        return True, 0
                    self.toggle_live_translation()
                    return True, 0
                elif hotkey_id == self.alt_k_hotkey_id:
                    self.set_api_key()
                    return True, 0
                elif hotkey_id == self.alt_l_hotkey_id:
                    self.set_target_language()
                    return True, 0
        return super().nativeEvent(eventType, message)


class TranslationWorker(QObject):
    finished = pyqtSignal(str, object, float)

    def __init__(self):
        super().__init__()
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="Translator"
        )

    def _execute_and_emit(
        self, region, source_lang, target_lang, history, last_hash, timestamp
    ):
        screenshot_np = capture_screen_region(region)
        if screenshot_np is None:
            self.finished.emit("", None, timestamp)
            return

        try:
            img_for_hash = Image.fromarray(screenshot_np)
            current_hash = imagehash.phash(img_for_hash)
            if current_hash == last_hash:
                self.finished.emit("", None, timestamp)
                return
            if current_hash in TRANSLATION_CACHE:
                self.finished.emit(
                    TRANSLATION_CACHE[current_hash], current_hash, timestamp
                )
                return
        except Exception as e:
            logging.error(f"Failed to hash image: {e}")
            current_hash = None

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            temp_path = tmp.name
            (
                img_for_hash
                if "img_for_hash" in locals()
                else Image.fromarray(screenshot_np)
            ).save(temp_path)

        try:
            result = gemini_translate_image_request(
                temp_path, source_lang, target_lang, history
            )
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass

        if current_hash:
            TRANSLATION_CACHE[current_hash] = result
            if len(TRANSLATION_CACHE) > MAX_CACHE_SIZE:
                TRANSLATION_CACHE.popitem(last=False)

        self.finished.emit(result, current_hash, timestamp)
        logging.info("Translation result: " + result.replace("\n", " | ")[:200])

    @pyqtSlot(tuple, str, str, list, object)
    def translate(self, region, source_lang, target_lang, history, last_hash):
        """Submits a new translation job to the thread pool."""
        timestamp = time.time()
        self.executor.submit(
            self._execute_and_emit,
            region,
            source_lang,
            target_lang,
            history,
            last_hash,
            timestamp,
        )

    def shutdown(self):
        self.executor.shutdown(wait=True)


class WinOCRMonitorThread(QThread):
    """Continuously OCRs a screen region and emits change_detected when text stabilizes.

    Emission logic:
    - After a new appearance: emit when the last two similarity checks >= sim_thresh.
    - Otherwise: require three consecutive similarity checks >= sim_thresh.
    - Debounced by EMIT_DEBOUNCE_SECONDS; near-duplicates (>= DUPLICATE_RATIO) are skipped.

    Tuned defaults suit subtitle-style text: short lines, frequent updates.
    """

    change_detected = pyqtSignal()

    def __init__(
        self,
        region,
        lang="en",
        interval=OCR_INTERVAL_DEFAULT,
        sim_thresh=OCR_SIM_THRESH_DEFAULT,
    ):
        super().__init__()
        self.region = region
        self.lang = lang
        self.interval = interval
        self.sim_thresh = sim_thresh
        logging.info(
            f"WinOCRMonitorThread initialized with lang={self.lang}, interval={self.interval}, sim_thresh={self.sim_thresh}"
        )

        self._running = True
        self._prev_text = None
        self._prev_prev_text = None
        self._prev_prev_prev_text = None
        self._last_emitted_text = None
        self._recent_appearance = False
        self._last_change_time = time.time()
        self._last_emit_time = 0.0

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            t0 = time.time()

            frame = capture_screen_region(self.region)
            if frame is None:
                time.sleep(self.interval)
                continue

            t1 = time.time()

            try:
                ocr_result = recognize_cv2_sync(frame, self.lang)
                curr_text = (
                    ocr_result.get("text")
                    if isinstance(ocr_result, dict)
                    else ocr_result
                ).strip()
                logging.info(f"WinOCR OCR: {curr_text}")
            except Exception as e:
                logging.error(f"WinOCR failed: {e}")
                time.sleep(self.interval)
                continue

            t2 = time.time()

            if not curr_text:
                if self._prev_text:
                    self._recent_appearance = False
                self._prev_prev_prev_text = self._prev_prev_text
                self._prev_prev_text = self._prev_text
                self._prev_text = curr_text
                time.sleep(self.interval)
                continue

            emit = False
            if self._prev_text is not None:
                sim = SequenceMatcher(None, curr_text, self._prev_text).ratio()
                sim_prev = 0.0
                if self._prev_prev_text is not None:
                    sim_prev = SequenceMatcher(
                        None, self._prev_text, self._prev_prev_text
                    ).ratio()
                sim_prev_prev = 0.0
                if self._prev_prev_prev_text is not None:
                    sim_prev_prev = SequenceMatcher(
                        None, self._prev_prev_text, self._prev_prev_prev_text
                    ).ratio()

                if not self._prev_text and curr_text:
                    self._recent_appearance = True
                    self._last_change_time = time.time()

                is_duplicate = False
                if self._last_emitted_text:
                    dup_ratio = SequenceMatcher(
                        None, curr_text, self._last_emitted_text
                    ).ratio()
                    if dup_ratio >= DUPLICATE_RATIO:
                        is_duplicate = True

                t3 = time.time()

                time_since_change = time.time() - self._last_change_time
                timing_log = f"Timings(ms): Capture={int((t1 - t0) * 1000)}, OCR={int((t2 - t1) * 1000)}, Logic={int((t3 - t2) * 1000)}. Since change: {time_since_change:.2f}s"

                if is_duplicate:
                    logging.info(
                        f"Skipping near-duplicate (ratio {dup_ratio:.2f}). {timing_log}"
                    )
                else:
                    if self._recent_appearance:
                        if sim >= self.sim_thresh and sim_prev >= self.sim_thresh:
                            emit = True
                            logging.info(f"Quick two-check emission. {timing_log}")
                            self._recent_appearance = False
                    else:
                        if (
                            sim >= self.sim_thresh
                            and sim_prev >= self.sim_thresh
                            and sim_prev_prev >= self.sim_thresh
                        ):
                            emit = True
                            logging.info(f"Full stability emission. {timing_log}")

                if not emit and not is_duplicate:
                    logging.info(f"Chain below threshold. {timing_log}")

            if emit:
                now = time.time()
                if now - self._last_emit_time < EMIT_DEBOUNCE_SECONDS:
                    logging.info(f"Debounce: Too soon after last emit; skipping.")
                else:
                    self.change_detected.emit()
                    self._last_emitted_text = curr_text
                    self._last_emit_time = now
                    self._last_change_time = now

            self._prev_prev_prev_text = self._prev_prev_text
            self._prev_prev_text = self._prev_text
            self._prev_text = curr_text

            elapsed = time.time() - t0
            sleep_time = self.interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


if __name__ == "__main__":
    app = QApplication([])
    translator_app = TranslatorApp()
    translator_app.show()

    try:
        raise SystemExit(app.exec_())
    except SystemExit:
        print("Application exited.")
