from PIL import Image, ImageDraw, ImageFilter
import requests
import pyautogui
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QSizeGrip, QShortcut, QLabel
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QThread, QObject, pyqtSlot, QMetaObject, QTimer
from PyQt5.QtGui import QTextCursor, QKeySequence
import sys
import tkinter as tk
from tkinter import simpledialog, Canvas
import logging
import time
import random
import asyncio
from google import genai
from google.genai import types
import ctypes
from ctypes import wintypes
import tempfile
import os
import itertools
import hashlib
import re
from difflib import SequenceMatcher
import threading
import collections
import imagehash
from winocr import recognize_cv2_sync
user32 = ctypes.windll.user32
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
MOD_ALT = 0x0001  # Alt key
# Virtual Key Codes
VK_OEM_3 = 0xC0  # ~ key
VK_0 = 0x30
VK_9 = 0x39
VK_ESCAPE = 0x1B
VK_OEM_PLUS = 0xBB
VK_OEM_MINUS = 0xBD
VK_T = 0x54  # 'T' key
VK_Q = 0x51  # 'Q' key
VK_K = 0x4B  # 'K' key
VK_L = 0x4C  # 'L' key
ALT_T_HOTKEY_ID = 1  # Hotkey ID for Alt+T visibility toggle
ALT_Q_HOTKEY_ID = 2  # Hotkey ID for Alt+Q select area
TILDE_HOTKEY_ID = 3  # Hotkey ID for '~' toggle live translation
PLUS_HOTKEY_ID = 4  # Hotkey ID for '+' increase font size
MINUS_HOTKEY_ID = 5  # Hotkey ID for '-' decrease font size
ALT_K_HOTKEY_ID = 6  # Hotkey ID for Alt+K set API key
ALT_L_HOTKEY_ID = 7  # Hotkey ID for Alt+L set language
# Window positioning flags for no-activate topmost overlay
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
# Extended style flags for ignoring Show Desktop (Win+D)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

# Low-level keyboard hook constants and structure
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

API_KEY = 'AIzaSyBOf37NOeSQ8tx3yKPawqjFjUbRc2_Jk8w'

# Globals for caching and rate-limit cooldowns
TRANSLATION_CACHE = collections.OrderedDict()
MAX_CACHE_SIZE = 100
MODEL_COOLDOWNS = {}
COOLDOWN_SECONDS = 60

_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite-preview-06-17",
    "gemini-2.5-flash",
    "gemini-2.5-flash-preview-04-17",
    "gemini-1.5-flash-8b",
    "learnlm-2.0-flash-experimental",
]
_model_cycle = itertools.cycle(_MODELS)
_current_model = next(_model_cycle)


def select_screen_region_with_mouse():
    print("Please select a part of the screen using the mouse.")
    region = {}

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.3)
    root.configure(bg="black")
    root.bind('<Escape>', lambda event: root.quit())
    root.focus_force()

    canvas = Canvas(root, cursor="cross", bg="black")
    canvas.pack(fill="both", expand=True)

    rect = None
    start_x = 0
    start_y = 0

    def on_mouse_press(event):
        nonlocal start_x, start_y, rect
        start_x = event.x
        start_y = event.y
        region['x1'] = event.x_root
        region['y1'] = event.y_root
        if not rect:
            rect = canvas.create_rectangle(0, 0, 0, 0, outline='red', width=2)
        canvas.coords(rect, start_x, start_y, start_x, start_y)

    def on_mouse_drag(event):
        canvas.coords(rect, start_x, start_y, event.x, event.y)

    def on_mouse_release(event):
        region['x2'] = event.x_root
        region['y2'] = event.y_root
        root.quit()

    canvas.bind("<ButtonPress-1>", on_mouse_press)
    canvas.bind("<B1-Motion>", on_mouse_drag)
    canvas.bind("<ButtonRelease-1>", on_mouse_release)

    root.mainloop()
    root.destroy()

    if 'x1' in region and 'y1' in region and 'x2' in region and 'y2' in region:
        x = min(region['x1'], region['x2'])
        y = min(region['y1'], region['y2'])
        width = abs(region['x2'] - region['x1'])
        height = abs(region['y2'] - region['y1'])
        print(
            f"Selected region: (X: {x}, Y: {y}, Width: {width}, Height: {height})")
        return (x, y, width, height)
    else:
        print("No region selected. Exiting.")
        return None


def capture_screen_region(region):
    # Prevent crash on zero-sized region (e.g., from a single click)
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

# The TranslationWorker now handles this logic directly.
# def process_screen_region_direct(region, source_lang, target_lang):
#     screenshot_np = capture_screen_region(region)
#     if screenshot_np is None:
#         return "Failed to capture screen"
#     with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
#         temp_path = tmp.name
#         cv2.imwrite(temp_path, screenshot_np)
#     translation = gemini_translate_image_request(
#         temp_path, source_lang, target_lang)
#     try:
#         os.remove(temp_path)
#     except Exception:
#         pass
#     return translation


def gemini_translate_image_request(image_path, from_lang, to_lang, history=None):
    """
    Translate the screenshot image directly via Gemini.
    Caching is now handled by the upstream TranslationWorker.
    """
    # 1. Caching is now handled by the worker, so this part is removed.
    # try:
    #     with open(image_path, 'rb') as f:
    #         image_bytes = f.read()
    #         image_hash = hashlib.sha256(image_bytes).hexdigest()
    # except IOError as e:
    #     logging.error(f"Could not read image file for hashing: {e}")
    #     return "Error: Cannot read image file"

    # if image_hash in TRANSLATION_CACHE:
    #     logging.info(f"Cache hit for image hash {image_hash[:10]}...")
    #     # Move to end to signify it was recently used
    #     TRANSLATION_CACHE.move_to_end(image_hash)
    #     return TRANSLATION_CACHE[image_hash]

    try:
        img = Image.open(image_path)
    except Exception as e:
        logging.error(f"Failed to open image for translation: {e}")
        return "Error: Cannot open image"

    prompt_header = (
        "SYSTEM:\n"
        "You are a high-accuracy multilingual translator. An IMAGE containing some text will be provided. "
        f"Translate EVERY piece of text you can read from **any language** into {to_lang.upper()} ONLY."
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
        "2. If the image has NO readable text, output an EMPTY string.\n"
        "3. Output **pure translated text** – no comments, no language tags, no explanations.\n"
        "4. DO NOT return English words unless they are part of proper names and must remain unchanged.\n"
        "5. Never output phrases like 'No text in the image' nor any apology."
    )

    prompt = prompt_header + context_prompt + prompt_footer
    # Pre-build unblock-all safety settings list once
    _SAFETY_OFF = [
        types.SafetySetting(
            category=cat, threshold=types.HarmBlockThreshold.BLOCK_NONE)
        for cat in (
            types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
        )
    ]

    client = genai.Client(api_key=API_KEY)

    # 2. Rate-limit-aware model rotation
    for model_name in _MODELS:
        # Check if model is on cooldown
        if model_name in MODEL_COOLDOWNS and time.time() < MODEL_COOLDOWNS[model_name]:
            logging.info(f"Model {model_name} is on cooldown. Skipping.")
            continue

        logging.info(f"Attempting translation with model: {model_name}")

        # Build low-latency config from scrtrans_bb.py
        cfg_kwargs = {
            "max_output_tokens": 96,  # subtitles rarely exceed 3 lines
            "temperature": 0.0,       # deterministic output
        }
        if "2.5" in model_name:
            # Zero thinking budget for 2.5 models to avoid extra delay
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=0)
        
        # Always define gen_config before the try block
        gen_config = types.GenerateContentConfig(
            **cfg_kwargs,
            safety_settings=_SAFETY_OFF
        )

        try:
            contents = [prompt, img]
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=gen_config
            )
            result = (response.text or "").strip()

            # Handle empty or no-text results
            if not result or result in ("No text in the image", "No text in the image."):
                logging.info(
                    f"Model {model_name} found no text or returned empty. Trying next model.")
                continue

            # If model returns English, treat as failure for this model and try next
            if re.fullmatch(r'^[A-Za-z0-9\s\.,!\?\:;\'"()\-]+$', result):
                logging.info(
                    f"English-only output from {model_name}; trying next model.")
                continue

            # Success!
            logging.info(f"Successful translation from {model_name}.")
            if result: # Success!
                return result

        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                logging.warning(
                    f"Rate limit hit for model {model_name}. Placing on cooldown for {COOLDOWN_SECONDS}s.")
                MODEL_COOLDOWNS[model_name] = time.time() + COOLDOWN_SECONDS
            else:
                logging.error(
                    f"Translation failed with model {model_name}: {e}")
            continue  # Try next model

    # If the loop completes, all models failed or are on cooldown.
    logging.error(
        "All models failed or are on cooldown. No translation available.")
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
    # Signal for the persistent worker thread (region, src, tgt, history, last_hash)
    translate_requested = pyqtSignal(tuple, str, str, list, object)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # Prevent this window from taking focus so games remain focused
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)

        screen_geometry = QApplication.primaryScreen().availableGeometry()
        width = 180
        height = 500
        self.setGeometry(screen_geometry.left(),
                         screen_geometry.bottom() - height, width, height)

        self.old_pos = None

        self.selected_region = None
        self.translation_in_progress = False
        self.font_sizes = [8, 9, 10, 11, 12, 13, 14,
                           15, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72]
        self.font_size_index = self.font_sizes.index(15)  # Default size 15
        self.intro_mode = True
        # Live translation toggle state
        self.live_translation = False
        # Default languages for live translation
        self.source_lang = 'en'
        self.target_lang = 'ar'
        # Keep reference to live thread to prevent premature destruction
        self.live_thread = None
        # Whether to show stop status after pending translation
        self.stop_pending = False
        # Flag to prevent multiple simultaneous area selections
        self.selecting = False
        # Last white-pixel count to detect text changes via ROI masking
        self.last_white_count = None
        # Timestamp of last translation to throttle API calls
        self.last_translation_time = 0.0
        # Cooldown period (seconds) between API calls to avoid consumption
        self.translation_cooldown = 1.0
        # Perceptual hash state for change detection
        self.last_image_hash = None  # store the last frame's hash
        self.hash_threshold = 8      # hamming distance threshold to trigger a new translation
        # Stability counter to ensure text area settles before translation
        self.stable_count = 0
        self.stable_required = 2  # number of stable frames before translation
        self.has_translated = False
        self.last_translation_result = None

        # Translation context: last 3 translations and hash of last processed image
        self.translation_history = collections.deque(maxlen=3)
        self.last_processed_hash = None
        
        # --- NEW: References to worker/monitor threads ---
        self.monitor_thread = None
        self.worker_thread = None
        self.worker = None
        
        # --- NEW: Dedicated status bar ---
        self.status_label = None
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.clear_status)

        self.placeholder_text = (
            "Transgemi\n\n"
            "Press '~' to translate the selected area.\n"
            "Press 'Alt+Q' to select an area to translate.\n"
            "Press 'Alt+K' to set your Gemini API key.\n"
            "Press 'Alt+L' to set the target language.\n"
            "Press '+' or '-' to change font size.\n"
            "Press 'Esc' to close."
        )

        self.init_ui()
        self.setup_hotkeys()
        self.show_placeholder()
        # Register global hotkey Alt+T for toggling visibility
        self.alt_t_hotkey_id = ALT_T_HOTKEY_ID
        # Use the main window handle so WM_HOTKEY is delivered to this window
        hwnd = int(self.winId())
        self.hwnd = hwnd
        # Make this a tool window so it's not hidden by Win+D
        try:
            orig_style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
            new_style = (orig_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, new_style)
        except Exception:
            pass
        if not user32.RegisterHotKey(hwnd, self.alt_t_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_T):
            logging.error("Failed to register global hotkey Alt+T")
        # Register global hotkey Alt+Q for selecting area
        self.alt_q_hotkey_id = ALT_Q_HOTKEY_ID
        if not user32.RegisterHotKey(hwnd, self.alt_q_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_Q):
            logging.error("Failed to register global hotkey Alt+Q")
        
        # Register global hotkey Tilde (~) for triggering translation
        self.tilde_hotkey_id = TILDE_HOTKEY_ID
        if not user32.RegisterHotKey(hwnd, self.tilde_hotkey_id, 0 | MOD_NOREPEAT, VK_OEM_3):
            logging.error("Failed to register global hotkey '~'")

        # Register global hotkey Alt+K for setting API Key
        self.alt_k_hotkey_id = ALT_K_HOTKEY_ID
        if not user32.RegisterHotKey(hwnd, self.alt_k_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_K):
            logging.error("Failed to register global hotkey Alt+K")

        # Register global hotkey Alt+L for setting language
        self.alt_l_hotkey_id = ALT_L_HOTKEY_ID
        if not user32.RegisterHotKey(hwnd, self.alt_l_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_L):
            logging.error("Failed to register global hotkey Alt+L")

        # NEW: Persistent background worker thread for translations
        self.worker_thread = QThread(self)
        self.worker = TranslationWorker()
        self.worker.moveToThread(self.worker_thread)
        self.worker.finished.connect(self.on_translation_finished)
        self.worker_thread.start()
        # Connect instance signal to worker slot
        self.translate_requested.connect(self.worker.translate)

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0) # No space between widgets

        self.text_edit = DraggableTextEdit(self)
        self.text_edit.setReadOnly(True)

        self.update_font_size()
        # Hide scrollbars
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(self.text_edit, 1) # Give it stretch factor of 1

        # Status indicator for live translation (red=off, green=on)
        self.status_indicator = QWidget(self.text_edit)
        self.status_indicator.setFixedSize(12, 12)
        self.status_indicator.move(5, 5)
        self.status_indicator.setStyleSheet(
            "background-color: red; border-radius: 6px;")
        self.status_indicator.show()

        self.sizegrip = QSizeGrip(self.text_edit)
        
        # Dedicated status label
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
        self.status_label.hide() # Hidden by default

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
        # Position size grip at bottom-right of the text_edit area.
        # The grip is a child of the text edit, so its position is relative.
        text_rect = self.text_edit.contentsRect()
        self.sizegrip.move(
            text_rect.right() - self.sizegrip.width(),
            text_rect.bottom() - self.sizegrip.height()
        )
        self.sizegrip.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_grip()

    def showEvent(self, event):
        super().showEvent(event)
        # Position grip on initial show
        self.position_grip()
        # Keep window topmost without stealing focus
        try:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE)
        except Exception:
            pass

    def mousePressEvent(self, event):
        # Start window drag by recording pointer offset from window top-left
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        # Move window while dragging to maintain pointer offset
        if hasattr(self, 'drag_offset') and self.drag_offset:
            self.move(event.globalPos() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        # End window drag
        self.drag_offset = None

    def set_api_key(self):
        global API_KEY
        # Hide the main window to ensure the dialog is focused
        self.hide()
        # Create a dummy root Tk window and withdraw it
        root = tk.Tk()
        root.withdraw()
        new_key = simpledialog.askstring("API Key", "Enter your Google Gemini API Key:", show='*')
        root.destroy()
        # Show the main window again
        self.show()

        self.show_placeholder()  # Reset UI
        if new_key:
            API_KEY = new_key.strip()
            logging.info("API Key updated.")
            self.append_status("API Key updated successfully.")
        else:
            logging.warning("API Key update cancelled.")
            self.append_status("API Key update cancelled.")

    def set_target_language(self):
        # Hide the main window to ensure the dialog is focused
        self.hide()
        # Create a dummy root Tk window and withdraw it
        root = tk.Tk()
        root.withdraw()
        new_lang = simpledialog.askstring("Target Language", "Enter target language code (e.g., 'en', 'ar', 'es'):", initialvalue=self.target_lang)
        root.destroy()
        # Show the main window again
        self.show()

        self.show_placeholder()  # Reset UI
        if new_lang:
            self.target_lang = new_lang.strip().lower()
            logging.info(f"Target language set to: {self.target_lang}")
            self.append_status(f"Target language changed to: {self.target_lang.upper()}")
        else:
            logging.warning("Target language update cancelled.")
            self.append_status("Language update cancelled.")

    def select_area(self):
        # Prevent opening multiple selection windows
        if self.selecting:
            return
        self.selecting = True

        # Stop any live translation for selection
        if self.live_translation:
            self.toggle_live_translation()

        self.intro_mode = False
        self.selected_region = select_screen_region_with_mouse()
        if self.selected_region:
            print(f"Selected region: {self.selected_region}")
            # Restart live translation after selecting new region
            self.toggle_live_translation()

        # Allow new selection after completion
        self.selecting = False

    def start_translation(self):
        self.intro_mode = False
        if self.translation_in_progress:
            logging.warning("Translation already in progress.")
            return

        if not self.selected_region:
            self.text_edit.setAlignment(Qt.AlignCenter)
            self.text_edit.setText("Please select an area first.")
            return

        self.translation_in_progress = True

        if self.text_edit.toPlainText() in (self.placeholder_text, "Please select an area first."):
            self.text_edit.clear()

        # Fire off translation request to the worker thread with context & hash
        self.translate_requested.emit(
            self.selected_region,
            self.source_lang,
            self.target_lang,
            list(self.translation_history),
            self.last_processed_hash)

    def on_translation_finished(self, result, processed_hash):
        # Early return when worker signals "no change" (hash unchanged)
        if processed_hash is None:
            self.translation_in_progress = False
            return

        # Store hash for next comparison
        self.last_processed_hash = processed_hash

        # Log and skip UI update when no text in the image
        no_text_english = ("No text in the image", "No text in the image.")
        no_text_arabic = ("لا يوجد نص في الصورة", "لا يوجد نص في الصورة.")
        normalized = result.strip()
        if not normalized or normalized in no_text_english or normalized in no_text_arabic:
            logging.info("No significant text found, skipping UI update.")
            self.translation_in_progress = False
            return

        # Prevent updating UI if the new translation is too similar to the last one
        if self.last_translation_result:
            similarity = SequenceMatcher(None, normalized, self.last_translation_result).ratio()
            # Skip only if (a) almost identical AND (b) not longer than previous.
            if similarity >= 0.85 and len(normalized) <= len(self.last_translation_result):
                logging.info(
                    f"Skipping update – similarity {similarity:.2f} and no additional content.")
                self.translation_in_progress = False
                return

        # Maintain history window
        self.translation_history.append(normalized)
        self.last_translation_result = normalized

        if self.text_edit.toPlainText():
            self.text_edit.append("")

        # Ensure widget layout is Right-to-Left for translations
        self.text_edit.setLayoutDirection(Qt.RightToLeft)
        self.text_edit.setAlignment(Qt.AlignRight)

        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_edit.setTextCursor(cursor)

        # Process each line individually to enforce RTL alignment on all lines
        lines = result.split('\\n')
        p_style = 'dir="rtl" style="margin: 0; padding: 0; line-height: 150%; text-align: right;"'

        # Create a <p> tag for each line of text, ensuring empty lines are rendered
        html_lines = [f'<p {p_style}>{line or "&nbsp;"}</p>' for line in lines]
        html_result = "".join(html_lines)

        self.text_edit.insertHtml(html_result)
        # Add blank line after translation for spacing
        self.text_edit.append("")

        self.text_edit.verticalScrollBar().setValue(
            self.text_edit.verticalScrollBar().maximum())
        self.translation_in_progress = False
        # Force the UI to process all pending events, including redraws
        QApplication.processEvents()

    def show_placeholder(self):
        self.text_edit.clear()
        self.text_edit.setText(self.placeholder_text)
        self.text_edit.setAlignment(Qt.AlignCenter)
        self.clear_status() # Also clear status bar

    def increase_font(self):
        self.intro_mode = False
        if self.font_size_index < len(self.font_sizes) - 1:
            self.font_size_index += 1
            self.update_font_size()

    def decrease_font(self):
        self.intro_mode = False
        if self.font_size_index > 0:
            self.font_size_index -= 1
            self.update_font_size()

    def setup_hotkeys(self):
        # The low-level hook handles the tilde key globally now, so this local shortcut is removed.
        # self.shortcut_translate = QShortcut(
        #     QKeySequence(Qt.Key_QuoteLeft), self)
        # self.shortcut_translate.setContext(Qt.WindowShortcut)
        # self.shortcut_translate.activated.connect(self.toggle_live_translation)

        # Local select area hotkey (Alt+Q)
        self.shortcut_select = QShortcut(QKeySequence("Alt+Q"), self)
        self.shortcut_select.activated.connect(self.select_area)

        self.shortcut_inc1 = QShortcut(QKeySequence("+"), self)
        self.shortcut_inc1.activated.connect(self.increase_font)
        self.shortcut_inc2 = QShortcut(QKeySequence("="), self)
        self.shortcut_inc2.activated.connect(self.increase_font)

        self.shortcut_dec = QShortcut(QKeySequence("-"), self)
        self.shortcut_dec.activated.connect(self.decrease_font)

        self.shortcut_close = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_close.activated.connect(self.close)

    def closeEvent(self, event):
        print("Closing application...")

        # Unregister other global hotkeys
        try:
            user32.UnregisterHotKey(self.hwnd, self.alt_t_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, self.alt_q_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, self.tilde_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, self.alt_k_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, self.alt_l_hotkey_id)
        except Exception:
            pass

        # Stop monitor and worker threads gracefully
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            self.monitor_thread.wait()

        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

        QApplication.quit()
        event.accept()

    def toggle_live_translation(self):
        self.live_translation = not self.live_translation
        if self.live_translation:
            if not self.selected_region:
                logging.warning("Cannot start live translation: No region selected.")
                self.live_translation = False  # Revert state
                self.append_status("Cannot start: Select a region with Alt+Q first.")
                return

            self.text_edit.clear()
            self.append_status("Live Translation Started")
            # Immediate first translation
            self.perform_live_translation()
            # Start the WinOCR-based monitor thread
            self.monitor_thread = WinOCRMonitorThread(
                self.selected_region,
                lang=self.source_lang,
                interval=0.2,
                sim_thresh=0.84
            )
            self.monitor_thread.change_detected.connect(self.perform_live_translation)
            self.monitor_thread.start()
            # Reset similarity tracking so identical lines can appear again in a new session
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
            f"background-color: {color}; border-radius: {radius}px;")

    def clear_status(self):
        self.status_label.setText("")
        self.status_label.hide()
        
    def append_status(self, text):
        # Shows a message in the dedicated status bar and clears it after a delay
        self.status_label.setText(text)
        self.status_label.show()
        self.status_timer.start(5000) # Clears after 5 seconds

    def perform_live_translation(self):
        """Slot for the monitor thread. Triggers a translation."""
        if not self.live_translation or self.translation_in_progress or not self.selected_region:
            return
        now = time.time()
        if self.last_translation_time and (now - self.last_translation_time) < self.translation_cooldown:
            return

        self.last_translation_time = now
        self.start_translation()

    def nativeEvent(self, eventType, message):
        # Handle global hotkeys
        if eventType == "windows_generic_MSG":
            msg = ctypes.cast(
                int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                if hotkey_id == self.alt_t_hotkey_id:
                    # Toggle visibility
                    if self.isVisible():
                        self.hide()
                    else:
                        self.show()
                        self.raise_()
                    return True, 0
                elif hotkey_id == getattr(self, 'alt_q_hotkey_id', None):
                    # Select translation area
                    self.select_area()
                    return True, 0
                elif hotkey_id == self.tilde_hotkey_id:
                    # Toggle live translation
                    self.toggle_live_translation()
                    return True, 0
                elif hotkey_id == self.alt_k_hotkey_id:
                    # Set API Key
                    self.set_api_key()
                    return True, 0
                elif hotkey_id == self.alt_l_hotkey_id:
                    # Set Target Language
                    self.set_target_language()
                    return True, 0
        return super().nativeEvent(eventType, message)


class TranslationWorker(QObject):
    """Long-lived worker object living in its own QThread."""

    finished = pyqtSignal(str, object)  # result, processed_hash

    @pyqtSlot(tuple, str, str, list, object)
    def translate(self, region, source_lang, target_lang, history, last_hash):
        """Heavy OCR + Gemini call executed off the GUI thread."""
        screenshot_np = capture_screen_region(region)
        if screenshot_np is None:
            # Signal no change so GUI can reset state
            self.finished.emit("", None)
            return

        # Compute perceptual hash for change detection / cache key
        try:
            img_for_hash = Image.fromarray(screenshot_np)
            current_hash = imagehash.phash(img_for_hash)

            if current_hash == last_hash:
                # Unchanged frame – emit special no-change signal
                self.finished.emit("", None)
                return

            # Cache lookup
            if current_hash in TRANSLATION_CACHE:
                self.finished.emit(TRANSLATION_CACHE[current_hash], current_hash)
                return
        except Exception as e:
            logging.error(f"Failed to hash image: {e}")
            current_hash = None

        # Save screenshot to temp file for Gemini request
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            temp_path = tmp.name
            (img_for_hash if 'img_for_hash' in locals() else Image.fromarray(screenshot_np)).save(temp_path)

        result = gemini_translate_image_request(
            temp_path, source_lang, target_lang, history)

        try:
            os.remove(temp_path)
        except Exception:
            pass

        # Cache new result
        if current_hash:
            TRANSLATION_CACHE[current_hash] = result
            if len(TRANSLATION_CACHE) > MAX_CACHE_SIZE:
                TRANSLATION_CACHE.popitem(last=False)

        self.finished.emit(result, current_hash)

        logging.info("Translation result: " + result.replace("\n", " | ")[:200])


class WinOCRMonitorThread(QThread):
    """Continuously OCRs a screen region using WinOCR and emits *change_detected*
    when two consecutive OCR results are highly similar (> sim_thresh).
    """

    change_detected = pyqtSignal()

    def __init__(self, region, lang='en', interval=0.2, sim_thresh=0.95):
        super().__init__()
        self.region = region
        self.lang = lang
        self.interval = interval
        self.sim_thresh = sim_thresh
        logging.info(f"WinOCRMonitorThread initialized with sim_thresh={self.sim_thresh}")

        self._running = True
        self._prev_text = None
        self._last_emitted_text = None

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            loop_start = time.time()

            frame = capture_screen_region(self.region)
            if frame is None:
                time.sleep(self.interval)
                continue

            try:
                ocr_result = recognize_cv2_sync(frame, self.lang)
                curr_text = (ocr_result.get('text') if isinstance(ocr_result, dict) else ocr_result).strip()
                logging.info(f"WinOCR OCR: {curr_text}")
            except Exception as e:
                logging.error(f"WinOCR failed: {e}")
                time.sleep(self.interval)
                continue

            if not curr_text:
                self._prev_text = curr_text
                time.sleep(self.interval)
                continue

            if self._prev_text is not None:
                sim = SequenceMatcher(None, curr_text, self._prev_text).ratio()
                if sim >= self.sim_thresh and curr_text != self._last_emitted_text:
                    self._last_emitted_text = curr_text
                    self.change_detected.emit()

            self._prev_text = curr_text

            # pacing
            elapsed = time.time() - loop_start
            sleep_time = self.interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    translator_app = TranslatorApp()
    translator_app.show()

    try:
        sys.exit(app.exec_())
    except SystemExit:
        print("Application exited.")
