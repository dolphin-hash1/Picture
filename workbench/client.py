from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

import websocket


class ComfyUIError(RuntimeError): pass
class ComfyUICancelled(ComfyUIError): pass

class ComfyUIClient:
    def __init__(self, server_address: str, timeout: float = 15):
        self.server_address = server_address.removeprefix("http://").removeprefix("https://").rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    @property
    def http_base(self) -> str: return f"http://{self.server_address}"

    def health_check(self) -> dict[str, Any]: return self._request_json("/system_stats")

    def checkpoints(self) -> list[str]:
        return self.input_choices("CheckpointLoaderSimple", "ckpt_name")

    def input_choices(self, class_type: str, input_name: str) -> list[str]:
        try:
            values = self._request_json(f"/object_info/{urllib.parse.quote(class_type)}")
            return list(values[class_type]["input"]["required"][input_name][0])
        except (KeyError, TypeError, ComfyUIError): return []

    def interrupt(self) -> None:
        try: self._request_json("/interrupt", method="POST", data={})
        except ComfyUIError: pass

    def execute(self, workflow: dict[str, Any], cancelled: Callable[[], bool], progress: Callable[[float, str], None]) -> list[bytes]:
        ws = websocket.WebSocket()
        try:
            try: ws.connect(f"ws://{self.server_address}/ws?clientId={self.client_id}", timeout=self.timeout)
            except (OSError, websocket.WebSocketException) as exc: raise ComfyUIError(f"无法连接 ComfyUI：{exc}") from exc
            response = self._request_json("/prompt", method="POST", data={"prompt": workflow, "client_id": self.client_id})
            prompt_id = response.get("prompt_id")
            if not prompt_id: raise ComfyUIError(f"ComfyUI 未返回任务编号：{response}")
            titles = {node_id: node.get("_meta", {}).get("title", node.get("class_type", f"节点 {node_id}")) for node_id, node in workflow.items() if isinstance(node, dict)}
            stage = "等待 ComfyUI 执行"
            ws.settimeout(1)
            deadline = time.monotonic() + 60 * 30
            while time.monotonic() < deadline:
                if cancelled(): self.interrupt(); raise ComfyUICancelled("任务已取消")
                try: raw = ws.recv()
                except (websocket.WebSocketTimeoutException, socket.timeout): continue
                except websocket.WebSocketException as exc: raise ComfyUIError(f"ComfyUI 连接中断：{exc}") from exc
                if not isinstance(raw, str): continue
                try: message = json.loads(raw)
                except json.JSONDecodeError: continue
                data = message.get("data", {})
                if data.get("prompt_id") != prompt_id: continue
                if message.get("type") == "executing":
                    node = data.get("node")
                    if node is None: break
                    stage = titles.get(str(node), f"节点 {node}"); progress(0, stage)
                elif message.get("type") == "progress":
                    maximum = data.get("max", 0)
                    value = data.get("value", 0)
                    progress(value / maximum if maximum else 0, f"{stage} · {value}/{maximum}")
            else: raise ComfyUIError("等待 ComfyUI 超时（30 分钟）。")
            return self._download_outputs(prompt_id)
        finally:
            try: ws.close()
            except Exception: pass

    def _download_outputs(self, prompt_id: str) -> list[bytes]:
        history = self._request_json(f"/history/{urllib.parse.quote(prompt_id)}")
        record = history.get(prompt_id)
        if not record: raise ComfyUIError("ComfyUI 未提供任务历史记录。")
        images: list[bytes] = []
        for output in record.get("outputs", {}).values():
            for image in output.get("images", []):
                params = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")})
                try:
                    with urllib.request.urlopen(f"{self.http_base}/view?{params}", timeout=self.timeout) as response: images.append(response.read())
                except (urllib.error.URLError, OSError) as exc: raise ComfyUIError(f"图片下载失败：{exc}") from exc
        if not images: raise ComfyUIError("工作流完成但没有产生图片输出。")
        return images

    def _request_json(self, path: str, method: str = "GET", data: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(f"{self.http_base}{path}", data=body, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response: return json.loads(response.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ComfyUIError(f"ComfyUI 请求 {path} 失败：{exc}") from exc
