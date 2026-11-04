"""Explicit, bounded microphone capture and local whisper.cpp transcription."""
from array import array
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Event, Thread
import time
import wave

from PySide6.QtCore import QBuffer, QIODevice, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices
from PySide6.QtWidgets import QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout
from .ui_theme import stylesheet


def pcm16_mono(raw, rate, channels, sample_format):
    """Convert supported Qt PCM formats to whisper's 16 kHz mono PCM16."""
    codes = {"Int16": ("h", 32768), "Int32": ("i", 2147483648), "Float": ("f", 1), "UInt8": ("B", 128)}
    if sample_format not in codes or rate <= 0 or channels <= 0:
        raise ValueError("Unsupported microphone format")
    code, scale = codes[sample_format]
    source = array(code)
    size = source.itemsize * channels
    source.frombytes(raw[:len(raw) // size * size])
    frames = len(source) // channels
    result = array("h")
    def mono(frame):
        offset = frame * channels
        value = sum(source[offset:offset+channels]) / channels
        return (value - 128) / 128 if sample_format == "UInt8" else value / scale
    for output in range(int(frames * 16000 / rate)):
        position = output * rate / 16000
        left = int(position)
        fraction = position - left
        value = mono(left) * (1-fraction) + mono(min(left+1, frames-1)) * fraction
        result.append(round(max(-1, min(1, value)) * 32767))
    return result.tobytes()


def transcribe(executable, model, pcm, *, runner=None, cancel=None, process_started=None):
    """Local process, no shell and no cloud request. Temporary audio is removed."""
    with tempfile.TemporaryDirectory(prefix="petlink-voice-") as folder:
        recording = Path(folder) / "command.wav"
        output = Path(folder) / "transcript"
        with wave.open(str(recording), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(pcm)
        args = [str(executable), "-m", str(model), "-f", str(recording),
                "-otxt", "-of", str(output), "-l", "auto", "-ng", "-t", "2"]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if runner is not None:
            code = runner(args, capture_output=True, timeout=120, creationflags=flags).returncode
        else:
            with subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags) as process:
                if process_started:
                    process_started(process)
                deadline = time.monotonic() + 120
                while process.poll() is None:
                    if (cancel and cancel.is_set()) or time.monotonic() >= deadline:
                        process.kill()
                        process.wait()
                        raise RuntimeError("Transcription stopped or timed out")
                    try:
                        process.wait(timeout=.1)
                    except subprocess.TimeoutExpired:
                        pass
                code = process.returncode
        if code != 0:
            raise RuntimeError("Local transcription failed. Check your whisper.cpp executable and model.")
        return output.with_suffix(".txt").read_text(encoding="utf-8").strip()[:6000]


class VoiceInput(QObject):
    busy = Signal(bool)
    text = Signal(str)
    status = Signal(str)
    completed = Signal(str, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.recording = False
        self.active = False
        self._source = None
        self._buffer = None
        self._closed = False
        self._cancel = Event()
        self._process = None
        self._worker = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.stop)
        self.completed.connect(self._completed)

    def configure(self, parent=None):
        dialog = QDialog(parent)
        dialog.setObjectName("chat")
        dialog.setWindowTitle("Local voice setup")
        dialog.setStyleSheet(stylesheet())
        layout = QVBoxLayout(dialog)
        note = QLabel("Choose whisper-cli.exe and a compatible ggml model. Voice stays on this laptop. The microphone starts only after you press it.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        fields = []
        for label, key, pattern in (("whisper.cpp", "whisper_executable", "Executable (*.exe);;All files (*)"),
                                    ("Speech model", "whisper_model", "Whisper model (*.bin);;All files (*)")):
            entry = QLineEdit(self.settings.value(key, ""))
            entry.setAccessibleName(label)
            row = QHBoxLayout()
            row.addWidget(entry)
            browse = QPushButton("Browse")
            def choose(checked=False, target=entry, title=label, file_filter=pattern):
                path, _ = QFileDialog.getOpenFileName(dialog, title, "", file_filter)
                if path:
                    target.setText(path)
            browse.clicked.connect(choose)
            row.addWidget(browse)
            form.addRow(label, row)
            fields.append((key, entry))
        layout.addLayout(form)
        error = QLabel()
        error.setWordWrap(True)
        layout.addWidget(error)
        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        save = QPushButton("Save voice setup")
        def accept():
            if not all(Path(entry.text()).is_file() for key, entry in fields):
                error.setText("Choose an existing executable and speech model file.")
                return
            for key, entry in fields:
                self.settings.setValue(key, entry.text())
            dialog.accept()
        save.clicked.connect(accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)
        dialog.resize(540, 240)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def toggle(self, parent=None):
        if self.recording:
            self.stop()
            return
        if self.active:
            self.status.emit("Transcribing locally. Please wait.")
            return
        executable = Path(self.settings.value("whisper_executable", ""))
        model = Path(self.settings.value("whisper_model", ""))
        if not executable.is_file() or not model.is_file():
            self.configure(parent)
            self.status.emit("Press the microphone again when voice setup is ready.")
            return
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.status.emit("No microphone found. Check Windows microphone permissions.")
            return
        audio_format = device.preferredFormat()
        if audio_format.sampleFormat().name not in ("Int16", "Int32", "Float", "UInt8"):
            self.status.emit("This microphone's format is not supported.")
            return
        self._format = (audio_format.sampleRate(), audio_format.channelCount(), audio_format.sampleFormat().name)
        self._paths = (executable, model)
        self._buffer = QBuffer(self)
        self._buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self._source = QAudioSource(device, audio_format, self)
        self._source.stateChanged.connect(self._audio_state)
        self.active = self.recording = True
        self._cancel.clear()
        self.busy.emit(True)
        self._source.start(self._buffer)
        if self.recording:
            self.status.emit("Listening… click the microphone to stop (30-second limit).")
            self.timer.start(30000)

    def _audio_state(self, state):
        if self._source and self._source.error() not in (QAudio.Error.NoError, QAudio.Error.UnderrunError):
            self.cancel()
            self.status.emit("Could not record. Check Windows microphone access and try again.")

    def _release_audio(self):
        self.timer.stop()
        if self._source:
            source, self._source = self._source, None
            source.stop()
            source.deleteLater()
        raw = bytes(self._buffer.data()) if self._buffer else b""
        if self._buffer:
            self._buffer.close()
            self._buffer.deleteLater()
            self._buffer = None
        self.recording = False
        return raw

    def stop(self):
        if not self.recording:
            return
        raw = self._release_audio()
        self.busy.emit(True)
        self.status.emit("Transcribing locally…")
        paths, audio_format = self._paths, self._format
        def work():
            try:
                pcm = pcm16_mono(raw, *audio_format)
                if len(pcm) < 3200:
                    raise ValueError("Recording was too short. Press the microphone and try again.")
                content, error = transcribe(*paths, pcm, cancel=self._cancel,
                    process_started=lambda process: setattr(self, "_process", process)), ""
            except Exception as exc:
                content = ""
                error = str(exc) if isinstance(exc, ValueError) else "Local voice transcription failed. Check voice setup and retry."
            try:
                self.completed.emit(content, error)
            except RuntimeError:
                pass
        self._worker = Thread(target=work, daemon=True)
        self._worker.start()

    def _completed(self, content, error):
        self.active = False
        self._process = None
        if self._closed:
            return
        self.busy.emit(False)
        self.status.emit(error or ("Review the transcript, then send." if content else "No speech recognized. Try again."))
        if content:
            self.text.emit(content)

    def cancel(self):
        self._cancel.set()
        self._release_audio()
        self.active = False
        self.busy.emit(False)

    def shutdown(self):
        self._closed = True
        self.cancel()
        if self._process and self._process.poll() is None:
            try:
                self._process.kill()
            except OSError:
                pass
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2)
