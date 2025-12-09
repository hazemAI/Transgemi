"""Language pack manager for Windows OCR.

Automatically detects and installs missing Windows OCR language packs
via PowerShell commands.
"""

import logging
import subprocess
from typing import Dict, List


# Mapping from common language codes to Windows OCR capability names
LANG_TO_CAPABILITY: Dict[str, str] = {
    "zh-CN": "Language.OCR~~~zh-CN~0.0.1.0",
    "zh-cn": "Language.OCR~~~zh-CN~0.0.1.0",
    "chinese": "Language.OCR~~~zh-CN~0.0.1.0",
    "zh-TW": "Language.OCR~~~zh-TW~0.0.1.0",
    "zh-tw": "Language.OCR~~~zh-TW~0.0.1.0",
    "ja": "Language.OCR~~~ja-JP~0.0.1.0",
    "ja-JP": "Language.OCR~~~ja-JP~0.0.1.0",
    "japanese": "Language.OCR~~~ja-JP~0.0.1.0",
    "en": "Language.OCR~~~en-US~0.0.1.0",
    "en-US": "Language.OCR~~~en-US~0.0.1.0",
    "english": "Language.OCR~~~en-US~0.0.1.0",
    "ar": "Language.OCR~~~ar-SA~0.0.1.0",
    "ar-SA": "Language.OCR~~~ar-SA~0.0.1.0",
    "arabic": "Language.OCR~~~ar-SA~0.0.1.0",
    "fr": "Language.OCR~~~fr-FR~0.0.1.0",
    "french": "Language.OCR~~~fr-FR~0.0.1.0",
    "de": "Language.OCR~~~de-DE~0.0.1.0",
    "german": "Language.OCR~~~de-DE~0.0.1.0",
    "es": "Language.OCR~~~es-ES~0.0.1.0",
    "spanish": "Language.OCR~~~es-ES~0.0.1.0",
    "ru": "Language.OCR~~~ru-RU~0.0.1.0",
    "russian": "Language.OCR~~~ru-RU~0.0.1.0",
}


def get_installed_ocr_languages() -> List[str]:
    """Get list of installed Windows OCR language packs.

    Returns:
        List of capability names (e.g., ['Language.OCR~~~en-US~0.0.1.0'])
        Empty list if query fails (e.g., permission denied)
    """
    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "Get-WindowsCapability -Online | Where-Object {$_.Name -like '*Language.OCR*' -and $_.State -eq 'Installed'} | Select-Object -ExpandProperty Name",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False
        )

        if result.returncode != 0:
            # Don't log as warning - permission errors are expected without admin
            logging.debug(
                "Cannot query Windows OCR capabilities (may need elevation): %s",
                result.stderr.split("\n")[0] if result.stderr else "Unknown error",
            )
            return []

        installed = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]
        logging.info("Installed OCR language packs: %s", installed)
        return installed

    except Exception as exc:
        logging.debug("Failed to query Windows OCR capabilities: %s", exc)
        return []


def ensure_language_pack(lang_code: str) -> bool:
    """Ensure a language pack is installed (graceful check, no auto-install).

    Args:
        lang_code: Language code (e.g., 'zh-CN', 'ja', 'japanese')

    Returns:
        Always True - we assume pack is available and let WinOCR fail naturally if not

    Note:
        This function no longer attempts to install packs (requires admin).
        If we can't verify due to permissions, we assume pack is installed.
        WinOCR will fail with clear error if pack is actually missing.
    """
    capability_name = LANG_TO_CAPABILITY.get(lang_code.lower())
    if not capability_name:
        logging.debug(
            "Unknown language code: %s, assuming pack is available", lang_code
        )
        return True

    # Try to check if installed (may fail due to permissions)
    installed = get_installed_ocr_languages()

    # If query failed (empty list, likely permission error), assume pack is installed
    if not installed:
        logging.debug(
            "Cannot verify language pack %s (no admin rights). "
            "Assuming it's installed - WinOCR will fail naturally if not.",
            lang_code,
        )
        return True

    # If we got a list and pack is in it, confirmed installed
    if capability_name in installed:
        logging.debug("Language pack %s verified as installed", capability_name)
        return True

    # Pack not in list - warn user but don't block
    logging.warning(
        "Language pack %s may not be installed. "
        "If WinOCR fails, install manually: Add-WindowsCapability -Online -Name '%s'",
        lang_code,
        capability_name,
    )
    return True  # Return True anyway, let WinOCR fail naturally if pack missing
