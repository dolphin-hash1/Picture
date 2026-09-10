import unittest
from unittest.mock import patch
from urllib.error import URLError

import websocket

from workbench.client import ComfyUIClient, ComfyUIError


class FakeSocket:
    def __init__(self, messages): self.messages = iter(messages)
    def connect(self, *_args, **_kwargs): pass
    def settimeout(self, _value): pass
    def recv(self): return next(self.messages)
    def close(self): pass


class ClientTests(unittest.TestCase):
    def test_execute_filters_events_and_returns_output(self):
        messages = [
            '{"type":"executing","data":{"prompt_id":"other","node":"1"}}',
            '{"type":"executing","data":{"prompt_id":"prompt-1","node":"5"}}',
            '{"type":"progress","data":{"prompt_id":"prompt-1","value":2,"max":4}}',
            '{"type":"executing","data":{"prompt_id":"prompt-1","node":null}}',
        ]
        client = ComfyUIClient("127.0.0.1:8188")
        client._request_json = lambda path, **_kwargs: {"prompt_id": "prompt-1"} if path == "/prompt" else {}
        client._download_outputs = lambda prompt_id: [b"image"]
        updates = []
        with patch("workbench.client.websocket.WebSocket", return_value=FakeSocket(messages)):
            result = client.execute({"5": {"class_type": "KSampler", "_meta": {"title": "Sampler"}}}, lambda: False, lambda value, stage: updates.append((value, stage)))
        self.assertEqual(result, [b"image"])
        self.assertIn((0.5, "Sampler · 2/4"), updates)

    def test_execute_reports_websocket_disconnection(self):
        class BrokenSocket(FakeSocket):
            def recv(self): raise websocket.WebSocketException("closed")
        client = ComfyUIClient("127.0.0.1:8188")
        client._request_json = lambda *_args, **_kwargs: {"prompt_id": "prompt-1"}
        with patch("workbench.client.websocket.WebSocket", return_value=BrokenSocket([])):
            with self.assertRaises(ComfyUIError): client.execute({}, lambda: False, lambda *_: None)

    def test_download_failure_is_actionable(self):
        client = ComfyUIClient("127.0.0.1:8188")
        client._request_json = lambda *_args, **_kwargs: {"job": {"outputs": {"1": {"images": [{"filename": "x.png"}]}}}}
        with patch("workbench.client.urllib.request.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(ComfyUIError, "图片下载失败"):
                client._download_outputs("job")
