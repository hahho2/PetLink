"""Opt-in hosted connections with fixed origins and native secret storage."""
import re
from dataclasses import replace
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit
from PySide6.QtCore import QSettings, QObject, Signal
from threading import Thread

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from .credentials import CredentialStore
from .models import ModelConfig
from .ui_theme import stylesheet

PROVIDERS = {"local": ("Local server", "http://127.0.0.1:11434"),
    "openai": ("OpenAI", "https://api.openai.com"),
    "grok": ("Grok", "https://api.x.ai"),
    "gemini": ("Google Gemini", "https://generativelanguage.googleapis.com")}


def local_config(address, model):
    parsed = urlsplit(address.strip())
    try:
        local = parsed.hostname == "localhost" or ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        local = False
    if (not local or parsed.scheme not in ("http", "https") or parsed.username
            or parsed.password or parsed.query or parsed.fragment
            or parsed.path.rstrip("/") not in ("", "/v1")):
        raise ValueError("Use a local address such as http://127.0.0.1:11434 or http://localhost:1234.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid server port.") from exc
    if not model.strip():
        raise ValueError("Enter the name of a model installed in your local server.")
    return ModelConfig(urlunsplit((parsed.scheme, parsed.netloc, "", "", "")),
                       model.strip(), timeout_seconds=120, max_tokens=1024)


def connection_details(values):
    """Validate public settings independently of session-only API credentials."""
    provider = values["provider"]
    if provider == "local":
        config = local_config(values["address"], values["model"])
        return replace(config, extra={"reasoning_effort": "none"}) if values.get("skip_thinking") else config
    if provider not in PROVIDERS or values["address"] != PROVIDERS[provider][1]:
        raise ValueError("Choose a supported provider and its official endpoint.")
    model = values["model"].strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,150}", model):
        raise ValueError("Enter the exact model ID from your provider's console.")
    return ModelConfig(values["address"], model, timeout_seconds=25,
        temperature=None, max_tokens=1024 if provider in ("grok", "gemini") else None,
        extra={"max_completion_tokens": 1024} if provider == "openai" else {})


def connection_config(values):
    config = connection_details(values)
    if values["provider"] == "local":
        return config
    if not values.get("consent"):
        raise ValueError("Enable cloud chat to send conversation text to this provider.")
    key = values.get("key", "").strip()
    if not key or any(c.isspace() for c in key) or len(key) > 1200:
        raise ValueError("Enter a valid API key without whitespace.")
    return replace(config, api_key=key)


def load_connection(settings, store, provider=None):
    provider = provider or settings.value("models/provider", "local")
    if provider not in PROVIDERS:
        provider = "local"
    prefix = "models/" + provider + "/"
    return dict(provider=provider, address=(settings.value(prefix + "address", PROVIDERS[provider][1])
        if provider == "local" else PROVIDERS[provider][1]),
        model=settings.value(prefix + "model", ""),
        consent=settings.value(prefix + "consent", False, type=bool),
        skip_thinking=settings.value(prefix + "skip_thinking", False, type=bool),
        key=store.read(provider) if provider != "local" else "")


def save_connection_details(settings, values):
    """Persist validated connection metadata only; key handling stays explicit."""
    connection_details(values)
    prefix = "models/" + values["provider"] + "/"
    for name in ("address", "model", "consent", "skip_thinking"):
        settings.setValue(prefix + name, values.get(name, False))
    settings.setValue("models/provider", values["provider"])
    settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError("Could not save model settings. Check that your settings folder is writable.")


class ConnectionSignals(QObject):
    ready = Signal(int, object, str, object)


class ModelSettings(QDialog):
    def __init__(self, settings, current, parent=None, *, store=None):
        super().__init__(parent)
        self.settings, self.store = settings, store or CredentialStore()
        self.connection = dict(current)
        self.drafts = {current["provider"]: dict(current)}
        self.setWindowTitle("AI Model Settings")
        self.setObjectName("chat")
        self.setStyleSheet(stylesheet())
        self.resize(540, 500)
        self._closed = False
        self._network_job = 0
        self._network = ConnectionSignals(self)
        self._network.ready.connect(self._network_ready)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.provider = QComboBox()
        for code, (label, _) in PROVIDERS.items():
            self.provider.addItem(label, code)
        self.address, self.model, self.key = QLineEdit(), QLineEdit(), QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.model.setPlaceholderText("Exact model ID from your server or provider")
        for label, widget in (("Provider", self.provider), ("Server", self.address),
                              ("Model", self.model), ("API key", self.key)):
            form.addRow(label, widget)
            widget.setAccessibleName(label)
        layout.addLayout(form)
        self.available = QComboBox()
        self.available.setAccessibleName("Available installed models")
        self.available.addItem("Refresh to discover installed models")
        self.available.activated.connect(lambda: self.model.setText(self.available.currentText()))
        form.addRow("Installed models", self.available)
        network_actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh models")
        self.refresh_button.clicked.connect(lambda: self._connect(True))
        self.test_button = QPushButton("Test connection")
        self.test_button.clicked.connect(lambda: self._connect(False))
        network_actions.addWidget(self.refresh_button)
        network_actions.addWidget(self.test_button)
        layout.addLayout(network_actions)
        self.network_status = QLabel("Not tested · no connection is made until you ask.")
        self.network_status.setWordWrap(True)
        layout.addWidget(self.network_status)
        self.consent = QCheckBox("Enable cloud chat with this provider")
        self.remember = QCheckBox("Remember key in Windows Credential Manager")
        self.skip_thinking = QCheckBox("Skip extended thinking (Ollama)")
        self.skip_thinking.setToolTip("For Ollama thinking models: reserve the response budget for answer text. Leave off for other local servers unless they support reasoning_effort=none.")
        layout.addWidget(self.consent)
        layout.addWidget(self.remember)
        advanced = QPushButton("Advanced options")
        advanced.setCheckable(True)
        self.advanced = QWidget()
        advanced_layout = QVBoxLayout(self.advanced)
        advanced_layout.addWidget(self.skip_thinking)
        self.advanced.hide()
        advanced.toggled.connect(self.advanced.setVisible)
        layout.addWidget(advanced)
        layout.addWidget(self.advanced)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        cancel, save = QPushButton("Cancel"), QPushButton("Save model settings")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        save.setObjectName("primary")
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)
        self._selected = current["provider"]
        self.provider.setCurrentIndex(self.provider.findData(self._selected))
        self._load(self._selected)
        self.provider.currentIndexChanged.connect(self._changed)

    def _connect(self, discover):
        from .models import create_provider, OpenAICompatibleProvider
        try:
            values = self._values()
            config = local_config(values["address"], values["model"] or "discovery") if discover else connection_config(values)
        except ValueError as exc:
            self.network_status.setText(str(exc))
            return
        self.refresh_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.network_status.setText("Checking local models…" if discover else "Testing connection…")
        self._network_snapshot = values
        self._network_job += 1
        job = self._network_job
        signals = self._network
        def work():
            try:
                if discover:
                    data = OpenAICompatibleProvider(config)._request("/models", None)
                    result = [m["id"] for m in data.get("data", []) if isinstance(m, dict) and isinstance(m.get("id"), str)][:200]
                    detail = f"{len(result)} installed models found." if result else "No models found. Install a model in your local server."
                else:
                    result = None
                    provider = create_provider("ollama" if values["provider"] == "local" else values["provider"], config)
                    detail = "Connected · model service is reachable." if provider.health_check() else "Connection failed. Check your server, model and API key."
            except Exception:
                result, detail = None, "Could not connect. Check that the server is running and the address is correct."
            try:
                signals.ready.emit(job, result, detail, values)
            except RuntimeError:
                pass
        Thread(target=work, daemon=True).start()

    def _network_ready(self, job, models, detail, snapshot):
        if self._closed or job != self._network_job:
            return
        self.refresh_button.setEnabled(self._selected == "local")
        self.test_button.setEnabled(True)
        if self._values() != snapshot:
            self.network_status.setText("Settings changed. Test or refresh again.")
            return
        self.network_status.setText(detail)
        if models is not None:
            self.available.clear()
            self.available.addItems(models)

    def reject(self):
        self._closed = True
        super().reject()

    def _values(self):
        return dict(provider=self._selected, address=self.address.text().strip(),
            model=self.model.text().strip(), key=self.key.text().strip(),
            consent=self.consent.isChecked(), remember=self.remember.isChecked(),
            skip_thinking=self.skip_thinking.isChecked())

    def _changed(self):
        self.drafts[self._selected] = self._values()
        self._selected = self.provider.currentData()
        self._load(self._selected)

    def _load(self, provider):
        self.error.clear()
        try:
            values = self.drafts.get(provider) or load_connection(self.settings, self.store, provider)
        except OSError:
            values = dict(address=PROVIDERS[provider][1], model="", key="", consent=False)
            self.error.setText("Could not read the saved key. Enter it again or use a local model.")
        self.address.setText(values["address"])
        self.model.setText(values["model"])
        self.key.setText(values.get("key", ""))
        self.consent.setChecked(values.get("consent", False))
        self.remember.setChecked(values.get("remember", bool(values.get("key"))))
        self.skip_thinking.setChecked(values.get("skip_thinking", False))
        cloud = provider != "local"
        self.refresh_button.setEnabled(not cloud)
        self.available.setEnabled(not cloud)
        self.address.setReadOnly(cloud)
        self.skip_thinking.setEnabled(not cloud)
        for widget in (self.key, self.consent, self.remember):
            widget.setEnabled(cloud)
        self.notice.setText("Cloud chat sends your message, recent history and task draft context to "
            + PROVIDERS[provider][0] + ". API charges may apply. Test connection checks service access without sending your chat."
            if cloud else "Chat stays on your local server. No API key is required.")

    def accept(self):
        values = self._values()
        try:
            connection_config(values)
            if values["provider"] != "local":
                if values["remember"]:
                    self.store.write(values["provider"], values["key"])
                else:
                    self.store.delete(values["provider"])
            save_connection_details(self.settings, values)
        except (ValueError, OSError) as exc:
            self.error.setText(str(exc))
            return
        self.connection = values
        self._closed = True
        super().accept()
