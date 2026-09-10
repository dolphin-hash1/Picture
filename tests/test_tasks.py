import tempfile
import time
import unittest

from cryptography.fernet import Fernet

from workbench.gallery import EncryptedGallery
from workbench.tasks import JobState, TaskManager
from workbench.workflow import GenerationOptions


class FakeClient:
    def execute(self, workflow, cancelled, progress):
        progress(0.5, "rendering")
        if cancelled():
            from workbench.client import ComfyUICancelled
            raise ComfyUICancelled("cancelled")
        return [b"result"]


class TaskTests(unittest.TestCase):
    def test_complete_and_cancel_pending_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = TaskManager(FakeClient, EncryptedGallery(folder, Fernet.generate_key()))
            first = manager.enqueue({"x": 1}, GenerationOptions(description="first"))
            second = manager.enqueue({"x": 2}, GenerationOptions(description="second"))
            manager.cancel(second.id)
            for _ in range(50):
                if manager._jobs[first.id].state == JobState.COMPLETED: break
                time.sleep(.02)
            self.assertEqual(manager._jobs[first.id].state, JobState.COMPLETED)
            self.assertEqual(manager._jobs[second.id].state, JobState.CANCELLED)
            self.assertEqual(len(manager.gallery.list_items()), 1)
            manager.close()
