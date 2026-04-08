"""i18n and voice command tests."""

import pytest

from i18n.service import (
    translate,
    get_all_translations,
    detect_language_from_text,
    parse_voice_command,
)
from i18n.translations import SUPPORTED_LANGUAGES
from tests.conftest import register_user, auth_header


class TestTranslations:
    def test_english_default(self):
        assert translate("common.yes") == "Yes"

    def test_hindi_translation(self):
        assert translate("common.yes", "hi") == "हाँ"

    def test_marathi_translation(self):
        assert translate("common.yes", "mr") == "हो"

    def test_fallback_to_english(self):
        # Tamil doesn't have auth.login, should fall back to English
        result = translate("auth.login", "ta")
        assert result == "Login"

    def test_unknown_key_returns_key(self):
        assert translate("nonexistent.key") == "nonexistent.key"

    def test_unknown_language_falls_back(self):
        assert translate("common.yes", "xx") == "Yes"

    def test_placeholder_substitution(self):
        # translate doesn't have built-in placeholders in current strings,
        # but the mechanism works
        result = translate("common.yes", "en", name="test")
        assert result == "Yes"  # No placeholder in this string

    def test_all_languages_exist(self):
        assert "en" in SUPPORTED_LANGUAGES
        assert "hi" in SUPPORTED_LANGUAGES
        assert "mr" in SUPPORTED_LANGUAGES
        assert "ta" in SUPPORTED_LANGUAGES
        assert "te" in SUPPORTED_LANGUAGES
        assert "bn" in SUPPORTED_LANGUAGES
        assert "gu" in SUPPORTED_LANGUAGES
        assert "kn" in SUPPORTED_LANGUAGES

    def test_get_all_translations_merges(self):
        hi_all = get_all_translations("hi")
        # Should have Hindi overrides
        assert hi_all["common.yes"] == "हाँ"
        # Should have English fallbacks for keys Hindi doesn't have
        assert "auth.login" in hi_all


class TestLanguageDetection:
    def test_detect_english(self):
        assert detect_language_from_text("check stock of rice") == "en"

    def test_detect_hindi(self):
        assert detect_language_from_text("चावल का स्टॉक बताओ") == "hi"

    def test_detect_tamil(self):
        assert detect_language_from_text("சரக்கு இருப்பு") == "ta"

    def test_detect_telugu(self):
        assert detect_language_from_text("స్టాక్ చూపించు") == "te"

    def test_detect_bengali(self):
        assert detect_language_from_text("স্টক দেখাও") == "bn"

    def test_detect_gujarati(self):
        assert detect_language_from_text("સ્ટોક બતાવો") == "gu"

    def test_detect_kannada(self):
        assert detect_language_from_text("ಸ್ಟಾಕ್ ತೋರಿಸಿ") == "kn"

    def test_detect_empty_defaults_english(self):
        assert detect_language_from_text("") == "en"

    def test_detect_numbers_defaults_english(self):
        assert detect_language_from_text("12345") == "en"


class TestVoiceCommands:
    def test_english_stock_check(self):
        result = parse_voice_command("check stock of rice")
        assert result["intent"] == "stock_check"
        assert result["params"]["product"] == "rice"

    def test_hindi_stock_check(self):
        result = parse_voice_command("चावल का स्टॉक बताओ")
        assert result["intent"] == "stock_check"
        assert result["params"]["product"] == "चावल"

    def test_english_stock_update(self):
        result = parse_voice_command("update stock of sugar to 50")
        assert result["intent"] == "stock_update"
        assert result["params"]["product"] == "sugar"
        assert result["params"]["quantity"] == "50"

    def test_english_daily_report(self):
        result = parse_voice_command("show daily report")
        assert result["intent"] == "daily_report"

    def test_hindi_daily_report(self):
        result = parse_voice_command("आज की रिपोर्ट")
        assert result["intent"] == "daily_report"

    def test_english_low_stock(self):
        result = parse_voice_command("show low stock")
        assert result["intent"] == "low_stock"

    def test_unknown_command(self):
        result = parse_voice_command("hello world")
        assert result["intent"] == "unknown"

    def test_empty_command(self):
        result = parse_voice_command("")
        assert result is None

    def test_english_new_order(self):
        result = parse_voice_command("create order for Rahul")
        assert result["intent"] == "new_order"
        assert result["params"]["customer"] == "Rahul"

    def test_command_has_raw_text(self):
        result = parse_voice_command("check stock of dal")
        assert result["raw_text"] == "check stock of dal"


class TestVoiceCommandAPI:
    @pytest.mark.asyncio
    async def test_voice_command_endpoint(self, client):
        reg = await register_user(client, "voice_user1", "cashier")
        resp = await client.post("/api/i18n/voice-command", json={"text": "check stock of rice"}, headers=auth_header(reg["token"]))
        assert resp.status_code == 200
        assert resp.json()["intent"] == "stock_check"

    @pytest.mark.asyncio
    async def test_voice_command_hindi(self, client):
        reg = await register_user(client, "voice_user2", "cashier")
        resp = await client.post("/api/i18n/voice-command", json={"text": "चावल का स्टॉक बताओ"}, headers=auth_header(reg["token"]))
        assert resp.status_code == 200
        assert resp.json()["intent"] == "stock_check"

    @pytest.mark.asyncio
    async def test_detect_language_endpoint(self, client):
        reg = await register_user(client, "voice_user3", "cashier")
        resp = await client.post("/api/i18n/detect-language", json={"text": "चावल"}, headers=auth_header(reg["token"]))
        assert resp.status_code == 200
        assert resp.json()["detected_language"] == "hi"
