"""
Main entry point for the translation application
"""

import sys
# Pre-import onnxruntime to prevent DLL load errors with PyQt5
try:
    import onnxruntime
except ImportError:
    pass

import logging
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from core.log_buffer import init_memory_logging
from core.translator_app import TranslatorApp


def setup_logging():
    """Configure logging for the application"""
    project_dir = Path(__file__).resolve().parent
    log_file = project_dir / "translator.log"
    formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    memory_handler = init_memory_logging(log_file)
    memory_handler.setFormatter(formatter)
    root_logger.addHandler(memory_handler)


def main():
    """Main entry point"""
    setup_logging()

    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)
        app.setApplicationName("Subtitle Translator")

        # Create and show the main window
        translator = TranslatorApp()
        translator.show()

        logging.info("Application started successfully")
        return app.exec_()

    except Exception as e:
        logging.error(f"Application failed to start: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
