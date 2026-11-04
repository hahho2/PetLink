"""Render a contact sheet and measure this machine's offscreen Qt frame cost."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import ctypes
import json
from pathlib import Path
import statistics
import time

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication
from petlink.pet_window import PetKind, PetWindow

app = QApplication([])
root = Path(__file__).resolve().parents[1]
pet = PetWindow(settings=QSettings(str(root / "preview-settings.ini"), QSettings.Format.IniFormat))
sheet = QImage(720, 280, QImage.Format.Format_ARGB32)
sheet.fill(QColor("#242333"))
painter = QPainter(sheet)
painter.setFont(QFont("Segoe UI", 12))
costs = []
for i, (kind, name) in enumerate(zip(PetKind, ("Coral", "Ishu", "Lola"))):
    pet._pet_kind = kind
    pet._tick()
    shot = pet.grab()
    painter.drawPixmap(i * 240, 0, shot)
    for _ in range(100):
        start = time.perf_counter()
        pet.grab()
        costs.append((time.perf_counter() - start) * 1000)
painter.end()
sheet.save(str(root / "pets-preview.png"))
pet.show()
samples = []
pet._animation.timeout.connect(lambda: samples.append(time.perf_counter()))
wall, cpu = time.perf_counter(), time.process_time()
QTimer.singleShot(3000, app.quit)
app.exec()
elapsed, used = time.perf_counter() - wall, time.process_time() - cpu
intervals = [(b-a)*1000 for a,b in zip(samples,samples[1:])]
report = {"mean_render_ms": round(statistics.mean(costs), 3),
          "p95_render_ms": round(sorted(costs)[int(len(costs)*.95)], 3),
          "timer_mean_ms": round(statistics.mean(intervals), 2),
          "cpu_one_core_percent": round(used / elapsed * 100, 2),
          "sample_seconds": round(elapsed, 2), "platform": "Qt offscreen, Windows CPU rendering"}
if os.name == "nt":
    class Memory(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [(key, ctypes.c_size_t) for key in
            ("peak", "working", "paged_peak", "paged", "nonpaged_peak", "nonpaged", "pagefile", "pagefile_peak")]
    info = Memory()
    info.cb = ctypes.sizeof(info)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.POINTER(Memory), ctypes.c_ulong)
    if ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(info), info.cb):
        report["working_set_mb"] = round(info.working / 1024**2, 1)
print(json.dumps(report, indent=2))
