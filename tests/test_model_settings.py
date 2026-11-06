import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from petlink.model_settings import ModelSettings, PROVIDERS, connection_config, load_connection, save_connection_details
from petlink.models import ChatMessage, GoogleGeminiProvider, create_provider
from petlink.chat_window import ChatWindow


class MemoryCredentials:
    def __init__(self):
        self.values = {}

    def read(self, provider):
        return self.values.get(provider, "")

    def write(self, provider, key):
        self.values[provider] = key

    def delete(self, provider):
        self.values.pop(provider, None)


class ModelSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.store = MemoryCredentials()

    def tearDown(self):
        self.folder.cleanup()

    def test_consent_and_fixed_origins_are_required(self):
        for provider in ("openai", "grok", "gemini"):
            values = dict(provider=provider, address=PROVIDERS[provider][1], model="test-model", key="dummy-key")
            with self.assertRaises(ValueError):
                connection_config(values)
            values["consent"] = True
            config = connection_config(values)
            self.assertNotIn("dummy-key", repr(config))
            self.assertIsNotNone(create_provider(provider, config))
            values["address"] = "https://other.example"
            with self.assertRaises(ValueError):
                connection_config(values)
        local = connection_config(dict(provider="local", address="http://localhost:1234/v1", model="test"))
        self.assertIsNone(local.api_key)

    def test_ollama_thinking_switch_is_optional_local_and_persisted(self):
        from petlink.chat_window import request_budget
        values = dict(provider="local", address="http://localhost:11434", model="qwen-test")
        self.assertEqual(connection_config(values).extra, {})
        values["skip_thinking"] = True
        config = connection_config(values)
        self.assertEqual(config.extra, {"reasoning_effort": "none"})
        self.assertEqual(config.timeout_seconds, 120)
        adapter = create_provider("ollama", config)
        self.assertEqual(request_budget(adapter), 180)
        dialog = ModelSettings(self.settings, values, store=self.store)
        dialog.accept()
        restored = load_connection(self.settings, self.store)
        self.assertTrue(restored["skip_thinking"])
        hosted = connection_config(dict(provider="openai", address=PROVIDERS["openai"][1],
            model="test-model", key="dummy-key", consent=True, skip_thinking=True))
        self.assertNotIn("reasoning_effort", hosted.extra)
        self.assertEqual(request_budget(create_provider("openai", hosted)), 90)

    def test_save_cancel_remember_and_remove_do_not_write_plaintext_keys(self):
        current = load_connection(self.settings, self.store)
        dialog = ModelSettings(self.settings, current, store=self.store)
        dialog.provider.setCurrentIndex(dialog.provider.findData("gemini"))
        dialog.model.setText("gemini-test")
        dialog.key.setText("dummy-secret")
        dialog.accept()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(self.store.values)
        dialog.consent.setChecked(True)
        dialog.remember.setChecked(True)
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.store.values["gemini"], "dummy-secret")
        contents = Path(self.settings.fileName()).read_text()
        self.assertNotIn("dummy-secret", contents)
        restored = load_connection(self.settings, self.store)
        self.assertEqual(restored["key"], "dummy-secret")
        dialog = ModelSettings(self.settings, restored, store=self.store)
        dialog.key.setText("cancelled-secret")
        dialog.reject()
        self.assertEqual(self.store.values["gemini"], "dummy-secret")
        dialog = ModelSettings(self.settings, restored, store=self.store)
        dialog.remember.setChecked(False)
        dialog.accept()
        self.assertNotIn("gemini", self.store.values)
        self.assertEqual(dialog.connection["key"], "dummy-secret")
        self.assertEqual(load_connection(self.settings, self.store)["key"], "")

    def test_key_store_failure_keeps_form_open_and_unsaved(self):
        current = dict(provider="openai", address=PROVIDERS["openai"][1],
            model="test-model", key="dummy-key", consent=True)
        dialog = ModelSettings(self.settings, current, store=self.store)
        with patch.object(self.store, "write", side_effect=OSError("Key store unavailable")):
            dialog.accept()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIn("unavailable", dialog.error.text())
        self.assertIsNone(self.settings.value("models/provider"))

    def test_inline_field_edits_restore_on_next_launch_and_blank_does_not_erase(self):
        self.settings.setValue("models/local/skip_thinking", True)
        dialog = ModelSettings(self.settings, load_connection(self.settings,self.store), store=self.store)
        dialog.show()
        dialog.activateWindow()
        self.app.processEvents()
        dialog.address.setFocus()
        dialog.address.selectAll()
        QTest.keyClicks(dialog.address, "http://localhost:1234/v1")
        dialog.model.setFocus()
        QTest.keyClicks(dialog.model, "my-last-model")
        dialog.accept()
        chat = ChatWindow(settings=self.settings)
        self.assertEqual(self.settings.value("models/local/model"), "my-last-model")
        chat.model.clear()
        chat.close()
        chat.shutdown()
        restored_settings = QSettings(self.settings.fileName(), QSettings.Format.IniFormat)
        restored = ChatWindow(settings=restored_settings)
        self.assertEqual(restored.model.text(), "my-last-model")
        self.assertEqual(restored.address.text(), "http://localhost:1234/v1")
        self.assertTrue(restored.connection["skip_thinking"])
        restored.shutdown()
        restored.hide()
        chat.deleteLater()
        restored.deleteLater()

    def test_used_and_unfocused_inline_values_are_remembered(self):
        chat = ChatWindow(settings=self.settings)
        chat.model.setText("used-model")
        self.assertIsNotNone(chat._provider())  # Build only: no network request.
        self.assertEqual(self.settings.value("models/local/model"), "used-model")
        chat.model.setText("last-model-before-exit")
        chat.shutdown()
        restored = ChatWindow(settings=QSettings(self.settings.fileName(), QSettings.Format.IniFormat))
        self.assertEqual(restored.model.text(), "last-model-before-exit")
        restored.shutdown()
        restored.hide()
        chat.hide()
        chat.deleteLater()
        restored.deleteLater()

    def test_inline_hosted_details_save_without_copying_session_key_or_consent(self):
        values = dict(provider="grok", address=PROVIDERS["grok"][1], model="original-model",
            consent=False, key="session-secret")
        save_connection_details(self.settings, values)
        with patch("petlink.chat_window.CredentialStore", return_value=self.store):
            chat = ChatWindow(settings=self.settings)
        chat.connection["key"] = "session-secret"
        chat.model.setText("new-hosted-model")
        chat.shutdown()
        restored = load_connection(self.settings, self.store)
        self.assertEqual(restored["provider"], "grok")
        self.assertEqual(restored["model"], "new-hosted-model")
        self.assertFalse(restored["consent"])
        self.assertEqual(restored["key"], "")
        self.assertNotIn("session-secret", Path(self.settings.fileName()).read_text())
        self.assertEqual(self.store.values, {})
        self.assertIsNone(chat._provider())  # Saving metadata did not authorize cloud calls.
        chat.hide()
        chat.deleteLater()

    def test_inline_save_failure_keeps_last_saved_connection_and_reports_error(self):
        save_connection_details(self.settings, dict(provider="local", address=PROVIDERS["local"][1], model="saved-model"))
        chat = ChatWindow(settings=self.settings)
        chat.model.setText("unsaved-model")
        with patch("petlink.chat_window.save_connection_details", side_effect=OSError()):
            self.assertIsNone(chat._provider())
            self.assertIn("Could not remember", chat.status.text())
        self.assertEqual(self.settings.value("models/local/model"), "saved-model")
        self.assertEqual(chat.model.text(), "unsaved-model")
        chat.hide()
        chat.deleteLater()

    def test_saved_thinking_choice_updates_live_provider_and_survives_reopen(self):
        chat = ChatWindow(settings=self.settings)
        chat.model.setText("qwen-test")
        current = {**chat.connection, "model": "qwen-test"}
        dialog = ModelSettings(self.settings, current, store=self.store)
        dialog.skip_thinking.setChecked(True)
        dialog.accept()
        with patch("petlink.chat_window.ModelSettings", return_value=dialog), patch.object(dialog, "exec", return_value=QDialog.DialogCode.Accepted):
            chat.model_settings()
        self.assertEqual(chat._provider().config.extra["reasoning_effort"], "none")
        self.assertIn("thinking skipped", chat.connection_note.toolTip())
        chat.shutdown()
        restored = ChatWindow(settings=QSettings(self.settings.fileName(), QSettings.Format.IniFormat))
        self.assertTrue(restored.connection["skip_thinking"])
        self.assertEqual(restored._provider().config.extra["reasoning_effort"], "none")
        restored.shutdown()
        restored.hide()
        chat.hide()
        restored.deleteLater()
        chat.deleteLater()

    def test_external_saved_thinking_change_is_not_overwritten_by_stale_chat_state(self):
        chat = ChatWindow(settings=self.settings)
        chat.model.setText("qwen-test")
        self.assertFalse(chat.connection["skip_thinking"])
        external = QSettings(self.settings.fileName(), QSettings.Format.IniFormat)
        external.setValue("models/local/skip_thinking", True)
        external.sync()
        self.assertEqual(chat._provider().config.extra["reasoning_effort"], "none")
        self.assertTrue(chat.connection["skip_thinking"])
        self.assertIn("thinking skipped", chat.connection_note.toolTip())
        chat.shutdown()
        self.assertTrue(load_connection(external, self.store)["skip_thinking"])
        chat.hide()
        chat.deleteLater()

    def test_provider_switch_preserves_form_drafts_and_chat_history(self):
        current = load_connection(self.settings, self.store)
        dialog = ModelSettings(self.settings, current, store=self.store)
        dialog.model.setText("my-local-model")
        dialog.provider.setCurrentIndex(dialog.provider.findData("grok"))
        self.assertEqual(dialog.key.text(), "")
        self.assertFalse(dialog.consent.isChecked())
        dialog.provider.setCurrentIndex(0)
        self.assertEqual(dialog.model.text(), "my-local-model")
        chat = ChatWindow(settings=self.settings)
        chat.history = [ChatMessage("user", "My plan")]
        chat.composer.setPlainText("Keep this draft")
        dialog.connection = dict(provider="grok", address=PROVIDERS["grok"][1],
            model="test-model", key="dummy-key", consent=True)
        with patch("petlink.chat_window.ModelSettings", return_value=dialog), patch.object(dialog, "exec", return_value=QDialog.DialogCode.Accepted):
            chat.model_settings()
        self.assertIn("messages leave this laptop", chat.connection_note.text())
        self.assertEqual(chat.composer.toPlainText(), "Keep this draft")
        self.assertEqual(chat.history[0].content, "My plan")
        self.assertEqual(chat._provider().config.api_key, "dummy-key")
        chat.shutdown()
        chat.hide()

    def test_gemini_auth_system_instruction_and_multipart_text(self):
        values = dict(provider="gemini", address=PROVIDERS["gemini"][1],
            model="gemini-test", key="dummy-key", consent=True)
        provider = GoogleGeminiProvider(connection_config(values))
        response = {"candidates": [{"content": {"parts": [{"text": "private", "thought": True}, {"text": "Hello"}, {"text": " world"}]}}]}
        with patch("petlink.models.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as request:
            result = provider.complete([ChatMessage("system", "Productivity only"), ChatMessage("user", "Plan")])
        sent = request.call_args.args[0]
        body = json.loads(sent.data)
        self.assertNotIn("dummy-key", sent.full_url)
        self.assertEqual(sent.get_header("X-goog-api-key"), "dummy-key")
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "Productivity only")
        self.assertEqual(body["contents"][0]["role"], "user")
        self.assertEqual(result.text, "Hello world")
        with patch("petlink.models.urlopen", return_value=io.BytesIO(b'{"name":"models/gemini-test"}')) as request:
            self.assertTrue(provider.health_check())
        self.assertIsNone(request.call_args.args[0].data)

    def test_hosted_compatible_auth_and_redirects(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from petlink.models import ModelConfig, OpenAICompatibleProvider, ModelError
        for provider in ("openai", "grok"):
            config = connection_config(dict(provider=provider, address=PROVIDERS[provider][1],
                model="test-model", key="dummy-key", consent=True))
            adapter = create_provider(provider, config)
            request = adapter._request_object("/chat/completions", adapter._payload(
                [ChatMessage("user", "Plan")], response_format=None))
            self.assertEqual(request.get_header("Authorization"), "Bearer dummy-key")
            self.assertNotIn("temperature", json.loads(request.data))
        paths = []
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/forwarded")
                self.end_headers()

            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            adapter = OpenAICompatibleProvider(ModelConfig(f"http://127.0.0.1:{server.server_port}", "test", api_key="dummy-key"))
            with self.assertRaises(ModelError):
                adapter._request("/models", None)
            self.assertEqual(paths, ["/v1/models"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
