from __future__ import annotations

import copy
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable

from .client import ComfyUICancelled, ComfyUIClient
from .gallery import EncryptedGallery
from .workflow import GenerationOptions


class JobState(str, Enum):
    QUEUED = "等待"; SUBMITTING = "提交中"; RUNNING = "生成中"; COMPLETED = "完成"; FAILED = "失败"; CANCELLED = "已取消"

@dataclass
class Job:
    id: str
    workflow: dict[str, Any]
    options: GenerationOptions
    state: JobState = JobState.QUEUED
    progress: float = 0
    stage: str = "等待处理"
    error: str = ""
    gallery_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    cancel_requested: bool = False


class TaskManager:
    """Single-worker local queue. Every Job owns an immutable workflow snapshot."""
    def __init__(self, client_factory: Callable[[], ComfyUIClient], gallery: EncryptedGallery, on_change: Callable[[Job], None] | None = None):
        self.client_factory, self.gallery, self.on_change = client_factory, gallery, on_change or (lambda _: None)
        self._pending: list[Job] = []; self._jobs: dict[str, Job] = {}; self._active: Job | None = None
        self._condition = threading.Condition(); self._closed = False
        self._thread = threading.Thread(target=self._worker, name="comfy-workbench", daemon=True); self._thread.start()

    def enqueue(self, workflow: dict[str, Any], options: GenerationOptions) -> Job:
        job = Job(uuid.uuid4().hex, copy.deepcopy(workflow), options)
        with self._condition: self._jobs[job.id] = job; self._pending.append(job); self._condition.notify()
        self._emit(job); return job

    def jobs(self) -> list[Job]:
        with self._condition: return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def cancel(self, job_id: str) -> None:
        with self._condition:
            job = self._jobs[job_id]
            if job.state == JobState.QUEUED:
                self._pending.remove(job); job.state = JobState.CANCELLED; job.stage = "已从队列移除"
            elif job is self._active and job.state in (JobState.SUBMITTING, JobState.RUNNING):
                job.cancel_requested = True; job.stage = "正在请求 ComfyUI 取消"
            else: return
        self._emit(job)

    def reorder(self, ordered_pending_ids: list[str]) -> None:
        with self._condition:
            existing = [job.id for job in self._pending]
            if sorted(existing) != sorted(ordered_pending_ids): raise ValueError("排序必须包含全部等待任务。")
            by_id = {job.id: job for job in self._pending}; self._pending = [by_id[job_id] for job_id in ordered_pending_ids]

    def retry(self, job_id: str) -> Job:
        with self._condition:
            old = self._jobs[job_id]
            if old.state not in (JobState.FAILED, JobState.CANCELLED): raise ValueError("只有失败或取消的任务可以重试。")
        return self.enqueue(old.workflow, old.options)

    def close(self) -> None:
        with self._condition: self._closed = True; self._condition.notify()

    def _worker(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._closed: self._condition.wait()
                if self._closed: return
                job = self._pending.pop(0); self._active = job; job.state = JobState.SUBMITTING; job.stage = "正在连接 ComfyUI"
            self._emit(job)
            client = self.client_factory()
            try:
                def report(value: float, stage: str) -> None:
                    job.state = JobState.RUNNING; job.progress = value; job.stage = stage; self._emit(job)
                images = client.execute(job.workflow, lambda: job.cancel_requested, report)
                if job.cancel_requested: raise ComfyUICancelled("任务已取消")
                for image in images:
                    item = self.gallery.save_image(image, {"job_id": job.id, "options": asdict(job.options), "created_at": time.time()})
                    job.gallery_ids.append(item.id)
                job.state = JobState.COMPLETED; job.progress = 1; job.stage = f"完成，已加密保存 {len(images)} 张图片"
            except ComfyUICancelled as exc:
                job.state = JobState.CANCELLED; job.error = str(exc); job.stage = "已取消"
            except Exception as exc:
                job.state = JobState.FAILED; job.error = str(exc); job.stage = "失败，可重试"
            finally:
                with self._condition: self._active = None
                self._emit(job)

    def _emit(self, job: Job) -> None: self.on_change(job)
