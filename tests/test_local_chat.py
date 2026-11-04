"""Exercise the real provider and chat worker against a loopback HTTP fixture."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
import unittest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from petlink.chat_window import ChatWindow


class Handler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"fixture"}]}')

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append((self.path, payload))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        events = ([{"error": {"message": "model missing"}}] if payload["model"] == "missing" else
                  [{"choices": []}, {"choices": [{"delta": {"role": "assistant"}}]},
                   {"choices": [{"delta": {"content": "Plan: focus for 25 minutes."}}]}])
        for event in events:
            self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")


class LocalChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_real_stream_and_server_error_recovery(self):
        chat = ChatWindow()
        chat.address.setText(f"http://127.0.0.1:{self.server.server_port}/v1")
        for model, expected in (("missing", "did not finish"), ("fixture", "Ready")):
            chat.model.setText(model)
            chat.composer.setPlainText("Help me plan")
            chat.send()
            deadline = time.monotonic() + 3
            while chat._busy and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertFalse(chat._busy)
            self.assertIn(expected, chat.status.text())
        self.assertIn("25 minutes", chat._reply_label.text())
        path, payload = Handler.requests[-1]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(payload["messages"][0]["role"], "system")
        chat.shutdown()
        chat.hide()
        chat.deleteLater()


if __name__ == "__main__":
    unittest.main()
