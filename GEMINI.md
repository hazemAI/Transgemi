# Project Summary

## Overview

- Desktop overlay that captures a user-selected screen region and streams translations for subtitles using configurable AI services
- Built with Python and PyQt5, providing a draggable translucent window for live subtitle display
- Includes OCR-based auto-translation mode with text stability detection and duplicate prevention

## Core Features

- Region selection overlay with Alt+Q and visual rubber-band feedback for choosing the subtitle area
- Hotkey-driven workflow for capture, translation trigger (~), API key entry (Alt+K), source language (Alt+L), service switching (Alt+S), visibility toggling (Alt+T), auto-translation toggle (Alt+~), and font size adjustment (+/-)
- Background worker that hashes captures, caches responses, and avoids duplicate translations for efficiency
- Auto-translation mode with OCR-based text stability detection (2-frame consistency check) and similarity-based duplicate rejection
- Source language selection (Alt+L) that routes to RapidOCR for Japanese/Chinese and WinOCR for English
- Translation services for Gemini, OpenRouter, Groq, SambaNova, and Cerebras, each handling image capture, hashing, and API calls with shared caching and rate-limit awareness plus aligned key-rotation error handling

## Architecture

### Core Layer (`core/`)

- **`TranslatorApp`**: Main overlay window managing hotkeys, screen capture, UI, and orchestration between OCR monitor and translation worker
- **`ConfigManager`**: Loads `.env` values (API keys, model name, temperature, cache limits, cooldowns, OCR settings)
- **`log_buffer`**: Application-level logging buffer for log display

### Services Layer (`services/`)

- **`TranslationServiceFactory`**: Chooses the appropriate translation backend based on configuration
- **Service Implementations**:
  - `GeminiTranslationService` (Google Generative AI client)
  - `OpenRouterTranslationService` (OpenRouter/OpenAI-compatible API client)
  - `GroqTranslationService` (Groq OpenAI-compatible API client)
  - `SambaNovaTranslationService` (SambaNova OpenAI-compatible API client)
  - `CerebrasTranslationService` (Cerebras OpenAI-compatible API client)

### Workers Layer (`workers/`)

- **`AutoOCRMonitor`**: Background QThread that continuously OCRs the selected region, emits `change_detected` when text stabilizes across 2 consecutive frames with similarity check
- **`TranslationWorker`**: QObject for background translation (manual mode ~, or receiving stable OCR from auto monitor)

### Subtitle/OCR Layer (`subtitle/`)

- **`subtitle_ocr`**: Dual-engine OCR extraction supporting WinOCR (Windows OCR) and RapidOCR with preprocessing (Otsu binarization, invert, padding)
- **`language_pack_manager`**: Detects and validates Windows OCR language packs for Chinese, Japanese, Korean, Arabic
- **`subtitle_image`**: Image processing utilities for subtitle extraction
- **`prompts`**: Translation prompt templates

## Dependencies

| Package                     | Purpose                                                                 |
| --------------------------- | ----------------------------------------------------------------------- |
| PyQt5==5.15.11              | Desktop GUI framework with widgets and threading support                |
| Pillow>=12.0.0              | Image manipulation for captured screenshots                             |
| pyautogui>=0.9.54           | Screen capture and automation utilities                                 |
| openai>=2.8.1               | OpenAI-compatible client used for OpenRouter, Groq, SambaNova, Cerebras |
| google-genai>=1.52.0        | Google Gemini API integration                                           |
| python-dotenv>=1.2.1        | Loads configuration from `.env` files                                   |
| imagehash>=4.3.2            | Perceptual hashing to prevent duplicate translations                    |
| numpy>=2.3.5                | Numerical operations for image processing                               |
| opencv-python>=4.11.0       | Image preprocessing (grayscale, Otsu, invert, padding) for OCR          |
| onnxruntime>=1.23.2         | ONNX model runtime for RapidOCR                                         |
| pywin32>=311                | Windows-specific integrations for hotkeys and window management         |
| winocr>=0.0.1               | Windows OCR integration (primary OCR engine)                            |
| rapidocr-onnxruntime>=1.4.4 | RapidOCR engine (fallback/alternative OCR with custom models)           |

## Configuration & Environment

Set the following environment variables in `.env` (defaults shown):

### Translation Service

- `TRANSLATION_SERVICE`

### AI Provider API Keys & Models

- `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_API_KEY_POOL`
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`, `OPENROUTER_API_KEY_POOL`, `OPENROUTER_DISABLE_REASONING_MODELS`
- `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_BASE_URL`, `GROQ_API_KEY_POOL`
- `SAMBANOVA_API_KEY`, `SAMBANOVA_MODEL`, `SAMBANOVA_BASE_URL`, `SAMBANOVA_API_KEY_POOL`
- `CEREBRAS_API_KEY`, `CEREBRAS_MODEL`, `CEREBRAS_BASE_URL`, `CEREBRAS_API_KEY_POOL`

### LLM Parameters

- `TEMPERATURE`, `MAX_TOKENS`, `TOP_P`, `FREQUENCY_PENALTY`, `PRESENCE_PENALTY`

### Translation Behavior

- `TRANSLATION_COOLDOWN`, `STATUS_CLEAR_MS`, `DUPLICATE_RATIO`, `MAX_CACHE_SIZE`, `COOLDOWN_SECONDS`
- `AUTO_TRANSLATION_ENABLED`, `AUTO_TRANSLATION_INTERVAL`

### OCR Settings (Subtitle Extraction)

- `SUBTITLE_OCR_DOWNSAMPLE_WIDTH`, `SUBTITLE_OCR_MIN_CONFIDENCE`, `SUBTITLE_OCR_MAX_LINES`

### OCR Monitor (Auto Mode)

- `OCR_MONITOR_INTERVAL` - Polling interval in seconds
- `OCR_SIMILARITY_THRESHOLD` - Minimum similarity to consider text stable
- `OCR_DUPLICATE_RATIO` - Similarity to reject near-duplicates
- `OCR_DEBOUNCE_SECONDS` - Minimum gap between emissions to prevent rapid-fire translations
- `SOURCE_LANGUAGE` - Source language for OCR engine selection: `ja`/`zh` use RapidOCR, `en` uses WinOCR

### UI Settings

- `FONT_SIZE`, `OVERLAY_WIDTH`, `OVERLAY_HEIGHT`

## Usage Flow

1. Launch the app (`python main.py`) to start the overlay window.
2. Press **Alt+Q** to select the subtitle region; confirm the selection prompt.
3. Press **Alt+L** to select source/target language.
4. Press **~** to trigger manual translation; the worker captures, OCRs, and calls the configured service.
5. Press **Alt+~** to toggle auto-translation mode.
6. Monitor translations in the overlay; cached results prevent duplicate API calls.
7. Use **Alt+S** to switch between Gemini, OpenRouter, Groq, SambaNova, and Cerebras, **Alt+K** to update API keys, and **Alt+T** to toggle visibility.

## Logging & Diagnostics

- Runtime events and errors are written to `translator.log` alongside console output for debugging
- Services emit structured logging for capture errors, rate limits, cooldowns, and translation outcomes
- OCR monitor logs stability checks, similarity ratios, and timing information

## TODO

- Solving the problem of auto mode latency
