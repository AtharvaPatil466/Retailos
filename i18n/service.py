"""i18n service — translate keys, detect language, parse voice commands."""

import re
from typing import Optional

from i18n.translations import TRANSLATIONS, DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


def translate(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Look up a translation key. Falls back to English, then returns the key itself."""
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANGUAGE])
    text = lang_dict.get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key) or key

    # Simple placeholder substitution: {name} -> value
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))

    return text


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Shorthand alias for translate()."""
    return translate(key, lang, **kwargs)


def get_all_translations(lang: str) -> dict[str, str]:
    """Return the full translation dict for a language, merged with English fallbacks."""
    base = dict(TRANSLATIONS.get(DEFAULT_LANGUAGE, {}))
    if lang != DEFAULT_LANGUAGE:
        base.update(TRANSLATIONS.get(lang, {}))
    return base


def detect_language_from_text(text: str) -> str:
    """Simple heuristic language detection based on Unicode script ranges."""
    # Count characters in different script ranges
    devanagari = len(re.findall(r'[\u0900-\u097F]', text))  # Hindi, Marathi
    tamil = len(re.findall(r'[\u0B80-\u0BFF]', text))
    telugu = len(re.findall(r'[\u0C00-\u0C7F]', text))
    bengali = len(re.findall(r'[\u0980-\u09FF]', text))
    gujarati = len(re.findall(r'[\u0A80-\u0AFF]', text))
    kannada = len(re.findall(r'[\u0C80-\u0CFF]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))

    scores = {
        "hi": devanagari,  # Could also be Marathi
        "ta": tamil,
        "te": telugu,
        "bn": bengali,
        "gu": gujarati,
        "kn": kannada,
        "en": latin,
    }

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return DEFAULT_LANGUAGE
    return best


# ── Voice Command Parsing ────────────────────────────────

# Maps Hindi/English voice command patterns to structured intents
VOICE_COMMAND_PATTERNS: dict[str, list[dict]] = {
    "stock_check": [
        {"lang": "en", "pattern": r"(?:check|show|what is|how much)\s+(?:stock|inventory)\s+(?:of|for)\s+(.+)", "extract": "product"},
        {"lang": "hi", "pattern": r"(.+)\s+(?:का|की|के)\s+(?:स्टॉक|माल)\s+(?:बताओ|दिखाओ|कितना)", "extract": "product"},
        {"lang": "hi", "pattern": r"(?:स्टॉक|माल)\s+(?:चेक|बताओ|दिखाओ)\s+(.+)", "extract": "product"},
    ],
    "stock_update": [
        {"lang": "en", "pattern": r"(?:update|set|change)\s+(?:stock|inventory)\s+(?:of|for)\s+(.+)\s+(?:to)\s+(\d+)", "extract": "product,quantity"},
        {"lang": "hi", "pattern": r"(.+)\s+(?:का|की|के)\s+(?:स्टॉक|माल)\s+(\d+)\s+(?:करो|कर दो|रखो)", "extract": "product,quantity"},
    ],
    "new_order": [
        {"lang": "en", "pattern": r"(?:new|create|add)\s+order\s+(?:for)\s+(.+)", "extract": "customer"},
        {"lang": "hi", "pattern": r"(.+)\s+(?:का|के लिए)\s+(?:नया|नई)\s+(?:ऑर्डर|बिल)", "extract": "customer"},
    ],
    "payment_received": [
        {"lang": "en", "pattern": r"(?:payment|received|got)\s+(?:from)\s+(.+)\s+(?:of|for|amount)\s+(\d+)", "extract": "customer,amount"},
        {"lang": "hi", "pattern": r"(.+)\s+(?:से|ने)\s+(\d+)\s+(?:रुपये|रुपए|₹)\s+(?:दिए|मिले|आए)", "extract": "customer,amount"},
    ],
    "daily_report": [
        {"lang": "en", "pattern": r"(?:show|get|today'?s?)\s+(?:daily|today'?s?)\s+(?:report|summary|sales)", "extract": ""},
        {"lang": "hi", "pattern": r"(?:आज|दिन)\s+(?:का|की|के)\s+(?:रिपोर्ट|बिक्री|हिसाब)", "extract": ""},
    ],
    "low_stock": [
        {"lang": "en", "pattern": r"(?:show|list|what)\s+(?:low stock|out of stock|reorder)", "extract": ""},
        {"lang": "hi", "pattern": r"(?:कम|खत्म)\s+(?:स्टॉक|माल)\s+(?:बताओ|दिखाओ|कौन)", "extract": ""},
    ],
}


def parse_voice_command(text: str) -> Optional[dict]:
    """Parse a voice command (Hindi or English) into a structured intent.

    Returns: {"intent": str, "params": dict, "lang": str} or None
    """
    text = text.strip()
    if not text:
        return None

    detected_lang = detect_language_from_text(text)

    for intent, patterns in VOICE_COMMAND_PATTERNS.items():
        for pat in patterns:
            match = re.search(pat["pattern"], text, re.IGNORECASE)
            if match:
                params = {}
                if pat["extract"]:
                    keys = pat["extract"].split(",")
                    for i, key in enumerate(keys):
                        if i < len(match.groups()):
                            params[key.strip()] = match.group(i + 1).strip()

                return {
                    "intent": intent,
                    "params": params,
                    "lang": pat["lang"],
                    "detected_lang": detected_lang,
                    "raw_text": text,
                }

    return {
        "intent": "unknown",
        "params": {},
        "lang": detected_lang,
        "detected_lang": detected_lang,
        "raw_text": text,
    }
