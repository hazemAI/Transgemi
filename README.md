# <img src="Transgemi.ico" alt="Transgemi Icon" width="48"> Transgemi - Screen Translator

## Demo

<video src="https://github.com/user-attachments/assets/90de884e-d1c1-4feb-a3d0-0878dfe68bf9" controls="controls" style="max-width: 720px;"></video>

A simple, on-the-fly screen translator that uses WinOCR (or RapidOCR for Asian languages) and LLM API services (Gemini, OpenRouter, Groq, etc.) to translate text from a selected area of your screen.

## Features

- **Multi-Engine OCR**: Automatically switches between Windows OCR (for Latin/Arabic/Japanese) and RapidOCR (for Chinese) for optimal accuracy.
- **Multiple AI Providers**: Support for Google Gemini, OpenRouter, Groq, SambaNova, and Cerebras.
- **Smart Auto-Translation**: Detects text stability to prevent flickering and duplicate translations.
- **Overlay UI**: Draggable, window that stays on top of your content.

## Installation

### Prerequisites

- Python 3.10 or higher.
- [uv](https://github.com/astral-sh/uv) (Recommended for fast package management) or standard `pip`.

### Setup

1.  Clone the repository or download the source code.
2.  Install dependencies:

    ```powershell
    # Using uv (Recommended)
    uv pip install .

    # Using standard pip
    pip install .
    ```

3.  Create a `.env` file in the project root (copy from `.env.example` if available) and add your API keys:
    ```env
    GEMINI_API_KEY=your_key_here
    # Add other keys as needed:
    # OPENROUTER_API_KEY=...
    # GROQ_API_KEY=...
    ```

## Usage

### Running the Application

```powershell
python main.py
```

### Hotkeys

| Hotkey          | Description                                                                                  |
| :-------------- | :------------------------------------------------------------------------------------------- |
| **`Alt + Q`**   | **Select Region**: Drag to select the screen area to translate.                              |
| **`~`** (Tilde) | **Manual Translate**: Trigger a one-time translation of the selected area.                   |
| **`Alt + ~`**   | **Toggle Auto-Translation**: Turn continuous translation on/off.                             |
| **`Alt + L`**   | **Language Settings**: Change source and target languages.                                   |
| **`Alt + S`**   | **Switch Service**: Cycle through available translation services (Gemini, OpenRouter, etc.). |
| **`Alt + K`**   | **Update API Key**: Quickly update the key for the current service.                          |
| **`Alt + T`**   | **Toggle Visibility**: Hide/Show the translation overlay.                                    |
| **`+` / `-`**   | **Font Size**: Increase or decrease text size.                                               |
| **`Esc`**       | **Exit**: Close the application.                                                             |

## Configuration

You can configure the application via the `.env` file. Key settings include:

- `TRANSLATION_SERVICE`: Translation service to use (e.g., `gemini`, `openrouter`, `groq`).
- `TARGET_LANGUAGE`: Target language (e.g., `English`).
- `OCR_MONITOR_INTERVAL`: How often to check for text changes in auto mode.
- `OCR_SIMILARITY_THRESHOLD`: Sensitivity for detecting text changes.

## Inspiration

This project was inspired by the excellent [Translumo](https://github.com/Danily07/Translumo) project.
