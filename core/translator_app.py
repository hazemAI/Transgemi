import pyautogui
import numpy as np
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QSizeGrip,
    QShortcut,
    QLabel,
    QInputDialog,
    QLineEdit,
    QGridLayout,
    QDialog,
    QComboBox,
    QFormLayout,
    QDialogButtonBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QEvent, QThread
from PyQt5.QtGui import QTextCursor, QKeySequence
import logging
import ctypes
from ctypes import wintypes
import collections

from core.config_manager import ConfigManager
from core.log_buffer import flush_logs
from .ui.draggable_text_edit import DraggableTextEdit
from .ui.region_selector import select_screen_region
from threads.translation_worker import TranslationWorker
from threads.auto_ocr_monitor import AutoOCRMonitor

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
MOD_ALT = 0x0001  # Alt key
# Virtual Key Codes
VK_OEM_3 = 0xC0  # ~ key
VK_T = 0x54  # 'T' key
VK_Q = 0x51  # 'Q' key
VK_K = 0x4B  # 'K' key
VK_L = 0x4C  # 'L' key
VK_S = 0x53  # 'S' key
ALT_T_HOTKEY_ID = 1  # Hotkey ID for Alt+T visibility toggle
ALT_Q_HOTKEY_ID = 2  # Hotkey ID for Alt+Q select area
TILDE_HOTKEY_ID = 3  # Hotkey ID for '~' toggle live translation
ALT_K_HOTKEY_ID = 6  # Hotkey ID for Alt+K set API key
ALT_L_HOTKEY_ID = 7  # Hotkey ID for Alt+L set language
ALT_S_HOTKEY_ID = 9  # Hotkey ID for Alt+S change service
ALT_TILDE_HOTKEY_ID = 10  # Hotkey ID for Alt+~ auto translation toggle
# Window positioning flags for no-activate topmost overlay
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
# Extended style flags for ignoring Show Desktop (Win+D)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000


class TranslatorApp(QMainWindow):
    """Topmost, draggable overlay that displays live translations."""

    translate_requested = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Initialize config first so we can use it for overlay dimensions
        self.config = ConfigManager()

        screen_geometry = QApplication.primaryScreen().availableGeometry()
        width = self.config.overlay_width
        height = self.config.overlay_height
        # Position with margin from edges to ensure it's fully visible
        self.setGeometry(
            screen_geometry.left(),
            screen_geometry.bottom() - height - 50,
            width,
            height,
        )
        self.selected_region = None
        self.font_sizes = list(range(8, 52, 2))  # 8px to 50px inclusive
        # Find closest font size index from config
        target_size = self.config.font_size
        closest_size = min(self.font_sizes, key=lambda x: abs(x - target_size))
        self.font_size_index = self.font_sizes.index(closest_size)
        # Flag to prevent multiple simultaneous area selections
        self.selecting = False
        # Timestamp of last translation to throttle API calls
        self.last_translation_time = 0.0
        self.last_translation_result = None
        self.last_update_timestamp = 0.0
        self.translation_history = collections.deque(maxlen=3)
        self.history_enabled = False
        self.last_processed_hash = None
        self.pending_translations = 0
        self.translation_cooldown = self.config.translation_cooldown
        self.auto_translation_interval = max(0.2, self.config.auto_translation_interval)
        self.auto_translation_enabled = self.config.auto_translation_enabled
        self.auto_translation_paused = False
        self.placeholder_active = False
        self.active_region_selector = None
        self.auto_state_text = ""
        self.auto_status_label = None
        self.auto_duplicate_threshold = 1
        self.last_auto_ocr_text = ""

        # Translation worker (runs in background thread, used by both manual and auto modes)
        self.translation_worker_thread = QThread()
        self.translation_worker = TranslationWorker(self.config)
        self.translation_worker.moveToThread(self.translation_worker_thread)
        self.translation_worker.translation_finished.connect(
            self.on_translation_finished
        )
        self.translation_worker.translation_error.connect(self.on_translation_error)
        self.translation_worker_thread.start()

        # OCR monitor for auto mode (created on demand, works with any OCR engine)
        self.ocr_monitor = None

        self.status_label = None
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.clear_status)

        self.placeholder_text = (
            "Transgemi - Subtitle Translator\n\n"
            "Press 'Alt+Q' to select subtitle area\n"
            "Press 'Alt+X' to cancel selection\n\n"
            "Press '~' to translate selected area\n\n"
            "Press 'Alt+~' to switch between auto/manual translation\n\n"
            "Press 'Alt+K' to set your API key\n\n"
            "Press '+' or '-' to change font size\n\n"
            "Press 'Alt+S' to switch translation service\n\n"
            "Press 'Alt+T' to show or hide window\n\n"
            "Press 'Esc' to close"
        )

        self.init_ui()
        self.setup_hotkeys()
        self.show_placeholder()
        QTimer.singleShot(100, self.register_global_hotkeys)
        self._refresh_auto_status_label()

        self.installEventFilter(self)

    def register_global_hotkeys(self):
        self.alt_t_hotkey_id = ALT_T_HOTKEY_ID
        hwnd = int(self.winId())
        self.hwnd = hwnd
        try:
            orig_style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
            new_style = (orig_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, new_style)
        except Exception:
            pass

        logging.info(f"Attempting to register hotkeys with window handle: {hwnd}")

        registrations = [
            (self.alt_t_hotkey_id, MOD_ALT | MOD_NOREPEAT, VK_T, "Alt+T"),
            (ALT_Q_HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_Q, "Alt+Q"),
            (TILDE_HOTKEY_ID, MOD_NOREPEAT, VK_OEM_3, "~"),
            (ALT_L_HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_L, "Alt+L"),
            (ALT_TILDE_HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_OEM_3, "Alt+~"),
            (ALT_K_HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_K, "Alt+K"),
            (ALT_S_HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_S, "Alt+S"),
        ]

        failed = []
        fallback_success = []
        for hotkey_id, modifiers, vk, label in registrations:
            user32.UnregisterHotKey(hwnd, hotkey_id)
            if user32.RegisterHotKey(hwnd, hotkey_id, modifiers, vk):
                continue

            error_code = ctypes.get_last_error()
            fallback_modifiers = (
                modifiers & ~MOD_NOREPEAT if modifiers & MOD_NOREPEAT else None
            )
            if fallback_modifiers is not None:
                ctypes.set_last_error(0)
                if user32.RegisterHotKey(hwnd, hotkey_id, fallback_modifiers, vk):
                    fallback_success.append((label, error_code))
                    continue
                error_code = ctypes.get_last_error() or error_code

            failed.append((label, error_code))

        for label, original_error in fallback_success:
            logging.warning(
                "Registered %s hotkey without MOD_NOREPEAT (initial error code: %s)",
                label,
                original_error,
            )

        if failed:
            for label, error_code in failed:
                logging.error(
                    "Failed to register %s hotkey - Error code: %s", label, error_code
                )
        else:
            logging.info("Successfully registered hotkeys")

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.auto_status_label = QLabel(self)
        self.auto_status_label.setAlignment(Qt.AlignCenter)
        self.auto_status_label.setStyleSheet(
            "QLabel { background-color: #202020; color: #ADD8E6; font-weight: bold; padding: 6px; }"
        )
        main_layout.addWidget(self.auto_status_label, 0)

        text_container = QWidget(self)
        text_container_layout = QGridLayout(text_container)
        text_container_layout.setContentsMargins(0, 0, 0, 0)
        text_container_layout.setSpacing(0)

        self.text_edit = DraggableTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.installEventFilter(self)

        self.update_font_size()
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        text_container_layout.addWidget(self.text_edit, 0, 0)

        main_layout.addWidget(text_container, 1)

        bottom_bar = QWidget(self)
        bottom_bar.setStyleSheet("background-color: black;")
        bottom_layout = QGridLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        self.status_label = QLabel(self)
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                color: #ADD8E6;
                font-style: italic;
                padding: 4px;
                font-size: 9pt;
            }
        """)
        self.status_label.setWordWrap(True)
        self.status_label.setFixedHeight(42)
        bottom_layout.addWidget(self.status_label, 0, 0)
        bottom_layout.setColumnStretch(0, 1)

        self.sizegrip = QSizeGrip(bottom_bar)
        self.sizegrip.setStyleSheet("QSizeGrip { background: transparent; }")
        bottom_layout.addWidget(self.sizegrip, 0, 1, Qt.AlignRight | Qt.AlignBottom)

        main_layout.addWidget(bottom_bar, 0)

    def update_font_size(self):
        font_size = self.font_sizes[self.font_size_index]
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: black;
                color: white;
                border: none;
                font-family: "Segoe UI", "Traditional Arabic", Tahoma, Arial, sans-serif;
                font-size: {font_size}px;
                font-weight: bold;
                padding-top: 20px;
                padding-left: 0px;
                padding-right: 0px;
            }}
            QScrollBar:vertical {{
                width: 0px;
            }}
            QScrollBar:horizontal {{
                height: 0px;
            }}
        """)

    def show_placeholder(self):
        self.text_edit.setText(self.placeholder_text)
        self.placeholder_active = True

    def setup_hotkeys(self):
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.handle_escape)

        plus_sequences = [
            QKeySequence("+"),
            QKeySequence("="),
            QKeySequence(Qt.Key_Plus),
        ]
        self.plus_shortcuts = [QShortcut(seq, self) for seq in plus_sequences]
        for shortcut in self.plus_shortcuts:
            shortcut.activated.connect(self.increase_font_size)
            shortcut.setContext(Qt.ApplicationShortcut)

        minus_sequences = [
            QKeySequence("-"),
            QKeySequence(Qt.Key_Minus),
            QKeySequence(Qt.Key_Underscore),
        ]
        self.minus_shortcuts = [QShortcut(seq, self) for seq in minus_sequences]
        for shortcut in self.minus_shortcuts:
            shortcut.activated.connect(self.decrease_font_size)
            shortcut.setContext(Qt.ApplicationShortcut)

    def handle_escape(self):
        selector = getattr(self, "active_region_selector", None)
        if selector is not None and selector.isVisible():
            selector.reject()
            return

        if self.selecting:
            self.show_status("Selection cancelled")
            return

        self.close()

    def select_region(self):
        if self.selecting:
            logging.info("Area selection already in progress")
            return
        self.selecting = True
        region = select_screen_region(self)
        self.selecting = False
        self.active_region_selector = None
        if region:
            self.selected_region = region
            self.show_status(
                f"Region selected: {region[2]}x{region[3]} - Press '~' to translate"
            )
            if self.auto_translation_enabled:
                self._start_auto_translation()
        else:
            self.show_status("Selection cancelled")

    def capture_screen_region(self, region):
        """Capture a screen region and return as numpy array."""
        if not region or region[2] <= 0 or region[3] <= 0:
            logging.warning(
                f"Invalid screen region provided: {region}. Skipping capture."
            )
            return None
        try:
            screenshot = pyautogui.screenshot(region=region)
            return np.array(screenshot)
        except Exception as exc:
            logging.error(f"Error capturing screen region: {exc}")
            return None

    def translate_selected(self):
        """Handle ~ key press: manual translation or auto mode pause/resume."""
        if self.auto_translation_enabled:
            # In auto mode, ~ toggles pause/resume
            self.auto_translation_paused = not self.auto_translation_paused
            if self.auto_translation_paused:
                self._stop_auto_translation()
                self.auto_state_text = "Auto translation paused (press '~' to resume)"
                self.show_status(self.auto_state_text, persistent=True)
                self._refresh_auto_status_label()
            else:
                self.last_translation_time = 0.0
                if self.selected_region is None:
                    self.auto_state_text = ""
                    self.show_status(
                        "Select a region to resume auto mode", persistent=True
                    )
                else:
                    self.auto_state_text = ""
                    self._start_auto_translation()
                self._refresh_auto_status_label()
            return

        # Manual mode: trigger one-shot translation
        if not self.selected_region:
            self.show_status("No region selected - Press Alt+Q to select area")
            return

        if self.selecting:
            self.show_status("Please wait for area selection to complete")
            return

        try:
            # Capture frame
            screenshot_np = pyautogui.screenshot(region=self.selected_region)
            screenshot_np = np.array(screenshot_np)

            # Reserve slot for pending counter
            self._reserve_translation_slot()

            self.translation_worker.translate_frame(screenshot_np, self.selected_region)

        except Exception as exc:
            logging.error("Manual translation failed: %s", exc)
            self.show_status(f"Error: {exc}")

    def on_translation_finished(self, translation_text, timestamp, image_hash):
        if timestamp < self.last_update_timestamp:
            self._update_pending_after_completion()
            return
        self.last_update_timestamp = timestamp

        if translation_text:
            cleaned_text = translation_text.strip()
            last_text = (self.last_translation_result or "").strip()
            if cleaned_text and cleaned_text == last_text:
                self._update_pending_after_completion()
                return

            if self.placeholder_active:
                self.text_edit.setText(translation_text)
                self.placeholder_active = False
            elif self.text_edit.toPlainText().strip():
                self.text_edit.append("\n" + translation_text)
            else:
                self.text_edit.setText(translation_text)
            self.last_translation_result = translation_text

            if self.history_enabled:
                self.translation_history.append(translation_text)
            self.last_processed_hash = image_hash
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.text_edit.setTextCursor(cursor)
            self.text_edit.ensureCursorVisible()
            self._update_pending_after_completion()
        else:
            if image_hash:
                self.last_processed_hash = image_hash
            self._update_pending_after_completion("No text detected in selected area")

    def on_translation_error(self, error_message):
        if (
            self.auto_translation_enabled
            and "no text detected" in error_message.lower()
        ):
            self._update_pending_after_completion()
            return
        self._update_pending_after_completion(f"Error: {error_message}")
        self.last_auto_ocr_text = ""

    def set_api_key(self):
        current_service = self.config.translation_service
        current_key = ""
        if current_service == "gemini":
            current_key = self.config.gemini_api_key
        elif current_service == "openrouter":
            current_key = self.config.openrouter_api_key
        elif current_service == "groq":
            current_key = self.config.groq_api_key
        elif current_service == "sambanova":
            current_key = self.config.sambanova_api_key
        elif current_service == "cerebras":
            current_key = self.config.cerebras_api_key

        new_key, ok = QInputDialog.getText(
            self,
            "API Key",
            f"Enter {current_service.upper()} API key:",
            QLineEdit.Password,
            current_key,
        )
        if ok:
            if current_service == "gemini":
                self.config.gemini_api_key = new_key
            elif current_service == "openrouter":
                self.config.openrouter_api_key = new_key
            elif current_service == "groq":
                self.config.groq_api_key = new_key
            elif current_service == "sambanova":
                self.config.sambanova_api_key = new_key
            elif current_service == "cerebras":
                self.config.cerebras_api_key = new_key
            self.show_status(f"{current_service.upper()} API key updated")
            self._refresh_worker_services()

    def set_language(self):
        source_langs = ["en", "ar", "ja", "zh", "fr", "de", "es", "ru"]
        source_labels = [
            "English",
            "Arabic",
            "Japanese",
            "Chinese",
            "French",
            "German",
            "Spanish",
            "Russian",
        ]
        target_langs = ["en", "ar", "ja", "zh", "fr", "de", "es", "ru"]
        target_labels = [
            "English",
            "Arabic",
            "Japanese",
            "Chinese",
            "French",
            "German",
            "Spanish",
            "Russian",
        ]

        dialog = QDialog(self)
        dialog.setWindowTitle("Language Settings")
        layout = QFormLayout(dialog)

        source_combo = QComboBox()
        source_combo.addItems(source_labels)
        current_source = self.config.source_language
        if current_source in source_langs:
            source_combo.setCurrentIndex(source_langs.index(current_source))

        target_combo = QComboBox()
        target_combo.addItems(target_labels)
        current_target = self.config.target_language
        if current_target in target_langs:
            target_combo.setCurrentIndex(target_langs.index(current_target))

        layout.addRow("Source:", source_combo)
        layout.addRow("Target:", target_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            new_source = source_langs[source_combo.currentIndex()]
            new_target = target_langs[target_combo.currentIndex()]

            source_changed = new_source != self.config.source_language
            self.config.source_language = new_source
            self.config.target_language = new_target

            self.show_status(
                f"Source: {source_labels[source_combo.currentIndex()]}, Target: {target_labels[target_combo.currentIndex()]}"
            )

            if (
                source_changed
                and self.auto_translation_enabled
                and not self.auto_translation_paused
            ):
                self._stop_auto_translation()
                self._start_auto_translation()

    def change_service(self):
        services = ["gemini", "openrouter", "groq", "sambanova", "cerebras"]
        current_service = self.config.translation_service
        current_index = (
            services.index(current_service) if current_service in services else 0
        )

        selection, ok = QInputDialog.getItem(
            self,
            "Select Translation Service",
            "Choose the active translation service:",
            services,
            current_index,
            False,
        )

        if ok and selection:
            if selection == current_service:
                self.show_status(f"Service unchanged: {selection}")
                return

            self.config.translation_service = selection
            self._reload_translation_service()
            self.show_status(f"Service switched to: {selection}", persistent=True)

    def _reload_translation_service(self):
        try:
            self.config.translation_service = self.config.translation_service
            self._refresh_worker_services()
            logging.info(
                "Translation service reloaded: %s", self.config.translation_service
            )
        except Exception as exc:
            logging.error("Failed to switch service: %s", exc)
            self.show_status(f"Error switching service: {exc}", persistent=True)

    def _refresh_worker_services(self):
        """Refresh the translation service in the worker after config changes."""
        if hasattr(self, "translation_worker") and self.translation_worker:
            self.translation_worker.refresh_service()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def toggle_auto_translation_mode(self):
        self.auto_translation_enabled = not self.auto_translation_enabled
        if self.auto_translation_enabled:
            self.auto_translation_paused = False
            if self.selected_region is None:
                self.auto_state_text = ""
                self.show_status(
                    "Auto translation enabled - select a region", persistent=True
                )
            else:
                self.auto_state_text = ""
                self.show_status("Auto translation enabled", persistent=True)
                self._start_auto_translation()
        else:
            self.auto_translation_paused = False
            self._stop_auto_translation()
            self.auto_state_text = ""
            self.show_status("Manual translation mode (press '~' to translate)")
        self._refresh_auto_status_label()

    def _start_auto_translation(self) -> None:
        if (
            not self.auto_translation_enabled
            or self.auto_translation_paused
            or self.selected_region is None
        ):
            return

        # Stop existing monitor if there is one
        if self.ocr_monitor is not None:
            self.ocr_monitor.stop()
            self.ocr_monitor.wait(100)
            self.ocr_monitor = None

        # Create and start new OCR monitor thread
        self.ocr_monitor = AutoOCRMonitor(
            region=self.selected_region,
            capture_func=self.capture_screen_region,
            lang=self.config.ocr_monitor_lang,
            source_lang=self.config.source_language,
            interval=self.config.ocr_monitor_interval,
            sim_thresh=self.config.ocr_similarity_threshold,
            duplicate_ratio=self.config.ocr_duplicate_ratio,
            debounce_seconds=self.config.ocr_debounce_seconds,
        )
        self.ocr_monitor.change_detected.connect(self._on_ocr_change_detected)
        self.ocr_monitor.start()
        logging.info("Auto-translation OCR monitor started")

    def _stop_auto_translation(self) -> None:
        if self.ocr_monitor is not None:
            self.ocr_monitor.stop()
            self.ocr_monitor = None
            logging.info("Auto-translation OCR monitor stopped")

    def _on_ocr_change_detected(self, frame, ocr_data=None):
        """Handle change_detected signal from OCR monitor (text stabilized)."""
        if not self.auto_translation_enabled or self.auto_translation_paused:
            return

        # Skip if translation is already in progress (prevent flooding)
        if self.pending_translations > 0:
            return

        try:
            screenshot_np = frame
            if screenshot_np is None:
                return

            self._reserve_translation_slot()

            self.translation_worker.translate_frame(
                screenshot_np, self.selected_region, precomputed_ocr=ocr_data
            )

        except Exception as exc:
            logging.error("Auto translation failed: %s", exc)

    def increase_font_size(self):
        if self.font_size_index < len(self.font_sizes) - 1:
            self.font_size_index += 1
            new_size = self.font_sizes[self.font_size_index]
            self.config.font_size = new_size
            self.update_font_size()
            self.show_status(f"Font size: {new_size}px")

    def decrease_font_size(self):
        if self.font_size_index > 0:
            self.font_size_index -= 1
            new_size = self.font_sizes[self.font_size_index]
            self.config.font_size = new_size
            self.update_font_size()
            self.show_status(f"Font size: {new_size}px")

    def show_status(self, message, persistent=False):
        display = message or self.auto_state_text
        self.status_label.setText(display)
        if (
            self.pending_translations > 0
            or persistent
            or message.startswith("Translating...")
        ):
            self.status_timer.stop()
        else:
            self.status_timer.start(5000)

    def _refresh_auto_status_label(self) -> None:
        if not self.auto_status_label:
            return
        if self.auto_translation_enabled:
            if self.auto_translation_paused:
                text = "Auto Translation Mode: Paused"
            else:
                text = "Auto Translation Mode: On"
        else:
            text = "Auto Translation Mode: Off"
        self.auto_status_label.setText(text)

    def clear_status(self):
        if self.pending_translations == 0:
            self.status_label.setText("")

    def _update_translating_status(self):
        if self.pending_translations > 0:
            self.show_status(
                f"Translating... ({self.pending_translations})", persistent=True
            )
        else:
            self.clear_status()

    def _update_pending_after_completion(self, success_message: str | None = None):
        if self.pending_translations > 0:
            self.pending_translations -= 1
        if self.pending_translations > 0:
            self._update_translating_status()
        else:
            if success_message:
                self.show_status(success_message)
            else:
                self.clear_status()

    def _reserve_translation_slot(self) -> None:
        self.pending_translations += 1
        self._update_translating_status()
        QApplication.processEvents()

    def eventFilter(self, obj, event):
        # Ensure '+' and '-' are not swallowed by the shortcut system
        if (
            obj is self.text_edit or obj is self
        ) and event.type() == QEvent.ShortcutOverride:
            key = event.key()
            native_vk = getattr(event, "nativeVirtualKey", lambda: None)()
            key_text = event.text()
            if (
                key in (Qt.Key_Plus, Qt.Key_Equal, Qt.Key_Minus, Qt.Key_Underscore)
                or key_text in ("+", "-")
                or native_vk in (0xBB, 0x6B, 0xBD, 0x6D)
            ):
                event.accept()
                return True

        if (obj is self.text_edit or obj is self) and event.type() == QEvent.KeyPress:
            key_text = event.text()
            key = event.key()
            native_vk = getattr(event, "nativeVirtualKey", lambda: None)()
            if (
                key in (Qt.Key_Plus, Qt.Key_Equal)
                or key_text == "+"
                or native_vk in (0xBB, 0x6B)
            ):
                self.increase_font_size()
                return True
            if (
                key in (Qt.Key_Minus, Qt.Key_Underscore)
                or key_text == "-"
                or native_vk in (0xBD, 0x6D)
            ):
                self.decrease_font_size()
                return True
        return super().eventFilter(obj, event)

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = wintypes.MSG.from_address(message.__int__())
            if msg.message == WM_HOTKEY:
                if msg.wParam == self.alt_t_hotkey_id:
                    self.toggle_visibility()
                elif msg.wParam == ALT_Q_HOTKEY_ID:
                    self.select_region()
                elif msg.wParam == TILDE_HOTKEY_ID:
                    self.translate_selected()
                elif msg.wParam == ALT_L_HOTKEY_ID:
                    self.set_language()
                elif msg.wParam == ALT_TILDE_HOTKEY_ID:
                    self.toggle_auto_translation_mode()
                elif msg.wParam == ALT_K_HOTKEY_ID:
                    self.set_api_key()
                elif msg.wParam == ALT_S_HOTKEY_ID:
                    self.change_service()
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        """Clean up resources on application close."""
        try:
            user32.UnregisterHotKey(self.hwnd, self.alt_t_hotkey_id)
            user32.UnregisterHotKey(self.hwnd, ALT_Q_HOTKEY_ID)
            user32.UnregisterHotKey(self.hwnd, TILDE_HOTKEY_ID)
            user32.UnregisterHotKey(self.hwnd, ALT_L_HOTKEY_ID)
            user32.UnregisterHotKey(self.hwnd, ALT_TILDE_HOTKEY_ID)
        except Exception:
            pass

        # Stop auto translation monitor
        self._stop_auto_translation()

        # Cleanup translation worker thread
        if (
            hasattr(self, "translation_worker_thread")
            and self.translation_worker_thread.isRunning()
        ):
            self.translation_worker_thread.quit()
            self.translation_worker_thread.wait(2000)

        # Prune old log sessions (keep last 3) before flushing
        from core.log_buffer import prune_translator_log
        from pathlib import Path

        log_path = Path("translator.log")
        prune_translator_log(log_path, max_sessions=3)

        flush_logs()

        app = QApplication.instance()
        if app is not None:
            app.quit()
        event.accept()

    def resizeEvent(self, event):
        """Save overlay dimensions when window is resized."""
        super().resizeEvent(event)
        new_size = event.size()
        self.config.overlay_width = new_size.width()
        self.config.overlay_height = new_size.height()
