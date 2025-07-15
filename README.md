# <img src="Transgemi.ico" alt="Transgemi Icon" width="48"> Transgemi - Screen Translator

A simple, on-the-fly screen translator that uses Windows' built-in OCR and Google's Gemini AI to translate text from a selected area of your screen.

## How to Use

### Prerequisites
Make sure you have Python installed and the required libraries. You can install them using the `requirements.txt` file:
`pip install -r requirements.txt`

### Running the Application
There are two ways to run the application:

1.  **Directly with Python (Recommended for developers):**
    `python scrtrans.py`

2.  **Using the VBScript (For ease of use):**
    Double-click the `run_transgemi.vbs` file. This script runs the Python application in the background without opening a console window.

### Hotkeys
-   **`Alt + Q`**: Select a new area on the screen to translate.
-   **`~`** (Tilde key): Toggle live translation on or off for the selected area.
-   **`Alt + K`**: Set your Google Gemini API Key. A dialog will appear to paste your key.
-   **`Alt + L`**: Set the target language for translation (e.g., 'en' for English, 'es' for Spanish).
-   **`+` / `-`**: Increase or decrease the font size of the translated text.
-   **`Alt + T`**: Show or hide the translation window.
-   **`Esc`**: Close the application.

### API Key
This application requires a Google Gemini API key to function. You can generate a free key from [Google AI Studio](https://aistudio.google.com/app/apikey).

Use the `Alt + K` hotkey to enter your key into the application.

## How It Works
The tool captures the selected screen region, sends it to the Gemini AI for translation, and displays the result in a transparent, always-on-top window. It rotates through different Gemini models to manage API rate limits and caches results to improve performance.

## Inspiration
This project was inspired by the excellent [Translumo](https://github.com/Danily07/Translumo) project. 