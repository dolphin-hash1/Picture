import unittest
from pathlib import Path

from workbench.workflow import GenerationOptions, WorkflowValidationError, build_workflow, load_workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.base = load_workflow(Path(__file__).parents[1] / "workflow_api.json")

    def test_builds_independent_snapshot_with_fixed_seed(self):
        options = GenerationOptions(description="test", checkpoint="model.safetensors", width=512, height=512, random_seed=False, seed=42, quality="自定义", stage1_steps=22)
        built, snapshot = build_workflow(self.base, options)
        self.assertEqual(snapshot.seed, 42)
        self.assertEqual(built["1"]["inputs"]["ckpt_name"], "model.safetensors")
        self.assertEqual(built["5"]["inputs"]["seed"], 42)
        self.assertEqual(built["5"]["inputs"]["steps"], 22)
        self.assertNotEqual(self.base["4"]["inputs"]["width"], 512)

    def test_rejects_unsupported_dimensions(self):
        with self.assertRaises(WorkflowValidationError):
            build_workflow(self.base, GenerationOptions(description="x", width=511, height=512))

    def test_rejects_missing_mapped_node(self):
        altered = dict(self.base); altered.pop("17")
        with self.assertRaises(WorkflowValidationError): build_workflow(altered, GenerationOptions(description="x"))
