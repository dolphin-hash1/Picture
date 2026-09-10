from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


class WorkflowValidationError(ValueError):
    pass


@dataclass(frozen=True)
class GenerationOptions:
    description: str
    count: int = 1
    checkpoint: str = ""
    width: int = 720
    height: int = 1280
    quality: str = "平衡"
    positive_prompt: str = ""
    negative_prompt: str = ""
    stage1_steps: int = 40
    stage1_cfg: float = 5.5
    stage1_sampler: str = "euler_ancestral"
    stage2_steps: int = 30
    stage2_cfg: float = 5.5
    stage2_sampler: str = "euler_ancestral"
    upscale_model: str = ""
    upscale_scale: float = 0.375
    random_seed: bool = True
    seed: int = 0

    def with_quality(self) -> "GenerationOptions":
        presets = {"快速": (20, 15, 0.25), "平衡": (40, 30, 0.375), "高质量": (50, 35, 0.5)}
        if self.quality == "自定义": return self
        first, second, scale = presets.get(self.quality, presets["平衡"])
        return replace(self, stage1_steps=first, stage2_steps=second, upscale_scale=scale)


REQUIRED_NODES: dict[str, tuple[str, tuple[str, ...]]] = {
    "1": ("CheckpointLoaderSimple", ("ckpt_name",)), "2": ("CLIPTextEncode", ("text",)),
    "3": ("CLIPTextEncode", ("text",)), "4": ("EmptyLatentImage", ("width", "height", "batch_size")),
    "5": ("KSampler", ("seed", "steps", "cfg", "sampler_name")), "9": ("UpscaleModelLoader", ("model_name",)),
    "12": ("KSampler", ("seed", "steps", "cfg", "sampler_name")), "16": ("ImageScaleBy", ("scale_by",)),
    "17": ("LMStudioNode", ("user_message",)),
}


def load_workflow(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowValidationError(f"找不到工作流文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowValidationError(f"工作流不是有效 JSON：{exc.msg}") from exc
    validate_workflow(data)
    return data


def validate_workflow(workflow: dict[str, Any]) -> None:
    issues: list[str] = []
    for node_id, (class_type, inputs) in REQUIRED_NODES.items():
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            issues.append(f"缺少节点 {node_id}"); continue
        if node.get("class_type") != class_type: issues.append(f"节点 {node_id} 应为 {class_type}")
        actual_inputs = node.get("inputs")
        if not isinstance(actual_inputs, dict): issues.append(f"节点 {node_id} 没有 inputs"); continue
        for key in inputs:
            if key not in actual_inputs: issues.append(f"节点 {node_id} 缺少参数 {key}")
    if issues: raise WorkflowValidationError("；".join(issues))


def build_workflow(base_workflow: dict[str, Any], options: GenerationOptions) -> tuple[dict[str, Any], GenerationOptions]:
    validate_workflow(base_workflow)
    if not options.description.strip() and not options.positive_prompt.strip():
        raise WorkflowValidationError("请输入画面描述或正向提示词。")
    if not 1 <= options.count <= 10: raise WorkflowValidationError("生成数量必须在 1 到 10 之间。")
    if options.width < 64 or options.height < 64 or options.width % 8 or options.height % 8:
        raise WorkflowValidationError("宽高必须是大于等于 64 的 8 的倍数。")
    snapshot = options.with_quality()
    seed = random.randint(0, 10**15) if snapshot.random_seed else snapshot.seed
    snapshot = replace(snapshot, seed=seed, random_seed=False)
    workflow = copy.deepcopy(base_workflow)
    if snapshot.checkpoint: workflow["1"]["inputs"]["ckpt_name"] = snapshot.checkpoint
    workflow["4"]["inputs"].update(width=snapshot.width, height=snapshot.height, batch_size=1)
    workflow["17"]["inputs"]["user_message"] = snapshot.description
    if snapshot.positive_prompt.strip(): workflow["2"]["inputs"]["text"] = snapshot.positive_prompt.strip()
    if snapshot.negative_prompt.strip(): workflow["3"]["inputs"]["text"] = snapshot.negative_prompt.strip()
    workflow["5"]["inputs"].update(seed=seed, steps=snapshot.stage1_steps, cfg=snapshot.stage1_cfg, sampler_name=snapshot.stage1_sampler)
    workflow["12"]["inputs"].update(seed=seed, steps=snapshot.stage2_steps, cfg=snapshot.stage2_cfg, sampler_name=snapshot.stage2_sampler)
    if snapshot.upscale_model: workflow["9"]["inputs"]["model_name"] = snapshot.upscale_model
    workflow["16"]["inputs"]["scale_by"] = snapshot.upscale_scale
    return workflow, snapshot
