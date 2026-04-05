"""Localization and voice command API routes."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from i18n.translations import SUPPORTED_LANGUAGES
from i18n.service import (
    translate,
    get_all_translations,
    detect_language_from_text,
    parse_voice_command,
)

router = APIRouter(prefix="/api/i18n", tags=["i18n"])


class VoiceCommandRequest(BaseModel):
    text: str
    lang: str = ""  # If empty, auto-detect


@router.get("/languages")
async def list_languages():
    """List supported languages."""
    language_names = {
        "en": "English",
        "hi": "Hindi (हिन्दी)",
        "mr": "Marathi (मराठी)",
        "ta": "Tamil (தமிழ்)",
        "te": "Telugu (తెలుగు)",
        "bn": "Bengali (বাংলা)",
        "gu": "Gujarati (ગુજરાતી)",
        "kn": "Kannada (ಕನ್ನಡ)",
    }
    return {
        "languages": [
            {"code": code, "name": language_names.get(code, code)}
            for code in SUPPORTED_LANGUAGES
        ],
        "default": "en",
    }


@router.get("/translations/{lang}")
async def get_translations(lang: str):
    """Get all translations for a language (with English fallbacks)."""
    if lang not in SUPPORTED_LANGUAGES:
        return {"error": f"Unsupported language: {lang}", "supported": SUPPORTED_LANGUAGES}
    return {"lang": lang, "translations": get_all_translations(lang)}


@router.get("/translate")
async def translate_key(
    key: str = Query(..., description="Translation key (e.g. 'inventory.title')"),
    lang: str = Query("en", description="Language code"),
):
    """Translate a single key."""
    return {"key": key, "lang": lang, "text": translate(key, lang)}


@router.post("/detect-language")
async def detect_language(body: VoiceCommandRequest):
    """Detect the language of input text."""
    detected = detect_language_from_text(body.text)
    return {"text": body.text, "detected_language": detected}


@router.post("/voice-command")
async def process_voice_command(body: VoiceCommandRequest):
    """Parse a voice command (Hindi or English) into a structured intent.

    Supports commands like:
    - English: "check stock of rice", "update stock of sugar to 50"
    - Hindi: "चावल का स्टॉक बताओ", "चीनी का स्टॉक 50 करो"
    """
    result = parse_voice_command(body.text)
    if result is None:
        return {"intent": "empty", "message": translate("voice.not_understood", body.lang or "en")}

    # Add localized confirmation message
    lang = body.lang or result.get("detected_lang", "en")
    if result["intent"] != "unknown":
        result["message"] = translate("voice.command_executed", lang)
    else:
        result["message"] = translate("voice.not_understood", lang)

    return result
