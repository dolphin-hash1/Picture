from __future__ import annotations

import io
import json
import queue
import threading
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from .client import ComfyUIClient
from .config import DPAPIKeyStore, KeyProtectionError, Settings, SettingsStore
from .gallery import EncryptedGallery, GalleryItem
from .tasks import Job, JobState, TaskManager
from .workflow import GenerationOptions, WorkflowValidationError, build_workflow, load_workflow


class WorkbenchApp(ctk.CTk):
    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        self.store = SettingsStore(project_root)
        self.settings = self.store.load()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.gallery: EncryptedGallery | None = None
        self.manager: TaskManager | None = None
        self.workflow: dict = {}
        self.checkpoints: list[str] = []
        self.gallery_items: dict[str, GalleryItem] = {}
        self.thumbnail_buttons: dict[str, ctk.CTkButton] = {}
        self._gallery_loaded = False
        self.title("ComfyUI 创作工作台")
        self.geometry("1280x820")
        self.minsize(1060, 700)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._process_events)
        threading.Thread(target=self._startup_check, daemon=True).start()

    def _build_ui(self) -> None:
        side = ctk.CTkFrame(self, width=350, corner_radius=0); side.grid(row=0, column=0, sticky="nsew"); side.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(side, text="🎨 创作工作台", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, padx=20, pady=(24, 8), sticky="w")
        ctk.CTkButton(side, text="⚙ 设置", width=80, command=self._open_settings).grid(row=0, column=0, padx=20, pady=(24, 8), sticky="e")
        ctk.CTkLabel(side, text="画面描述").grid(row=1, column=0, padx=20, pady=(12, 3), sticky="w")
        self.description = ctk.CTkTextbox(side, height=130); self.description.grid(row=2, column=0, padx=20, sticky="ew")
        self.model_var = ctk.StringVar(value=self.settings.checkpoint or "检测中…")
        self._option(side, "模型", self.model_var, [self.model_var.get()], 3)
        self.size_var = ctk.StringVar(value="720 × 1280")
        self._option(side, "尺寸", self.size_var, ["512 × 512", "720 × 1280", "768 × 1024", "1024 × 1024", "1280 × 720"], 5)
        self.quality_var = ctk.StringVar(value="平衡")
        self._option(side, "质量", self.quality_var, ["快速", "平衡", "高质量", "自定义"], 7)
        self.count_var = ctk.StringVar(value="1")
        self._option(side, "数量", self.count_var, [str(i) for i in range(1, 11)], 9)
        self.advanced_open = False
        self.advanced_button = ctk.CTkButton(side, text="高级参数 ▸", fg_color="transparent", command=self._toggle_advanced)
        self.advanced_button.grid(row=11, column=0, padx=15, pady=(8, 0), sticky="w")
        self.advanced = ctk.CTkScrollableFrame(side, height=230); self.advanced.grid_columnconfigure(0, weight=1)
        self.positive = self._textbox(self.advanced, "正向提示词（填入后覆盖 LLM 输出）", 0)
        self.negative = self._textbox(self.advanced, "负向提示词", 2)
        self.s1_steps = self._entry(self.advanced, "第一阶段步数", "40", 4); self.s1_cfg = self._entry(self.advanced, "第一阶段 CFG", "5.5", 6)
        self.s1_sampler = self._entry(self.advanced, "第一阶段采样器", "euler_ancestral", 8)
        self.s2_steps = self._entry(self.advanced, "第二阶段步数", "30", 10); self.s2_cfg = self._entry(self.advanced, "第二阶段 CFG", "5.5", 12)
        self.s2_sampler = self._entry(self.advanced, "第二阶段采样器", "euler_ancestral", 14)
        self.upscale_model = self._entry(self.advanced, "放大模型（留空使用工作流默认值）", "", 16)
        self.upscale_scale = self._entry(self.advanced, "放大缩放比例", "0.375", 18)
        self.random_seed = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.advanced, text="随机种子", variable=self.random_seed, command=self._seed_toggle).grid(row=20, column=0, padx=4, pady=(7, 0), sticky="w")
        self.seed = self._entry(self.advanced, "固定种子", "0", 21); self.seed.configure(state="disabled")
        self.generate = ctk.CTkButton(side, text="🚀 加入生成队列", height=44, font=ctk.CTkFont(size=16, weight="bold"), command=self._enqueue)
        self.generate.grid(row=12, column=0, padx=20, pady=14, sticky="ew")
        self.progress = ctk.CTkProgressBar(side); self.progress.grid(row=13, column=0, padx=20, sticky="ew"); self.progress.set(0)
        self.status = ctk.CTkLabel(side, text="正在检查环境…", justify="left", wraplength=300, text_color="gray", height=65, anchor="w")
        self.status.grid(row=14, column=0, padx=20, pady=(8, 20), sticky="ew")

        self.tabs = ctk.CTkTabview(self); self.tabs.grid(row=0, column=1, padx=18, pady=18, sticky="nsew")
        self.current_tab = self.tabs.add("当前作品"); self.gallery_tab = self.tabs.add("加密图库"); self.tasks_tab = self.tabs.add("任务队列")
        self.current_tab.grid_rowconfigure(0, weight=1); self.current_tab.grid_columnconfigure(0, weight=1)
        self.preview = ctk.CTkLabel(self.current_tab, text="完成生成后，作品将在这里显示", font=ctk.CTkFont(size=18), text_color="gray")
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.gallery_tab.grid_rowconfigure(1, weight=1); self.gallery_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(self.gallery_tab, text="🔄 刷新图库", command=self._load_gallery).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.gallery_frame = ctk.CTkScrollableFrame(self.gallery_tab); self.gallery_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.tasks_tab.grid_rowconfigure(0, weight=1); self.tasks_tab.grid_columnconfigure(0, weight=1)
        self.tasks_frame = ctk.CTkScrollableFrame(self.tasks_tab); self.tasks_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

    def _option(self, parent, label, variable, values, row) -> None:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, padx=20, pady=(9, 2), sticky="w")
        menu = ctk.CTkOptionMenu(parent, variable=variable, values=values); menu.grid(row=row + 1, column=0, padx=20, sticky="ew")
        if label == "模型": self.model_menu = menu

    def _textbox(self, parent, label, row):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, padx=4, pady=(6, 2), sticky="w")
        box = ctk.CTkTextbox(parent, height=55); box.grid(row=row + 1, column=0, padx=4, sticky="ew"); return box

    def _entry(self, parent, label, value, row):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, padx=4, pady=(6, 1), sticky="w")
        entry = ctk.CTkEntry(parent); entry.insert(0, value); entry.grid(row=row + 1, column=0, padx=4, sticky="ew"); return entry

    def _toggle_advanced(self) -> None:
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.advanced.grid(row=10, column=0, padx=15, pady=(0, 4), sticky="ew"); self.advanced_button.configure(text="高级参数 ▾")
        else: self.advanced.grid_forget(); self.advanced_button.configure(text="高级参数 ▸")

    def _seed_toggle(self) -> None: self.seed.configure(state="disabled" if self.random_seed.get() else "normal")

    def _startup_check(self) -> None:
        try:
            workflow = load_workflow(self.settings.workflow_path)
            key = DPAPIKeyStore(self.store.app_dir).get_or_create()
            gallery = EncryptedGallery(self.settings.gallery_dir, key)
            client = ComfyUIClient(self.settings.server_address)
            client.health_check(); checkpoints = client.checkpoints(); warnings = []
            checkpoint = workflow["1"]["inputs"]["ckpt_name"]
            upscale = workflow["9"]["inputs"]["model_name"]
            if checkpoints and checkpoint not in checkpoints: warnings.append(f"工作流模型未在 ComfyUI 中发现：{checkpoint}")
            upscale_choices = client.input_choices("UpscaleModelLoader", "model_name")
            if upscale_choices and upscale not in upscale_choices: warnings.append(f"放大模型未在 ComfyUI 中发现：{upscale}")
            self.events.put(("ready", (workflow, gallery, checkpoints, warnings)))
        except Exception as exc: self.events.put(("startup_error", str(exc)))

    def _enqueue(self) -> None:
        if not self.manager: self._set_status("环境未就绪，请先检查设置和 ComfyUI 服务。", error=True); return
        try:
            width, height = [int(value.strip()) for value in self.size_var.get().split("×")]
            options = GenerationOptions(
                description=self.description.get("1.0", "end").strip(), count=int(self.count_var.get()), checkpoint=self.model_var.get(),
                width=width, height=height, quality=self.quality_var.get(), positive_prompt=self.positive.get("1.0", "end").strip(),
                negative_prompt=self.negative.get("1.0", "end").strip(), stage1_steps=int(self.s1_steps.get()), stage1_cfg=float(self.s1_cfg.get()),
                stage1_sampler=self.s1_sampler.get().strip(), stage2_steps=int(self.s2_steps.get()), stage2_cfg=float(self.s2_cfg.get()),
                stage2_sampler=self.s2_sampler.get().strip(), upscale_model=self.upscale_model.get().strip(), upscale_scale=float(self.upscale_scale.get()),
                random_seed=self.random_seed.get(), seed=int(self.seed.get()),
            )
            for _ in range(options.count):
                workflow, snapshot = build_workflow(self.workflow, options)
                self.manager.enqueue(workflow, snapshot)
            self._set_status(f"已加入 {options.count} 个任务。")
        except (ValueError, WorkflowValidationError) as exc: self._set_status(str(exc), error=True)

    def _on_job(self, job: Job) -> None: self.events.put(("job", job))

    def _process_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "ready":
                    self.workflow, self.gallery, self.checkpoints, warnings = payload
                    choices = self.checkpoints or [self.workflow["1"]["inputs"]["ckpt_name"]]
                    self.model_menu.configure(values=choices); chosen = self.settings.checkpoint if self.settings.checkpoint in choices else choices[0]
                    self.model_var.set(chosen)
                    self.manager = TaskManager(lambda: ComfyUIClient(self.settings.server_address), self.gallery, self._on_job)
                    self._set_status("；".join(warnings) if warnings else "已连接 ComfyUI，工作流与加密图库已就绪。", error=bool(warnings)); self._load_gallery()
                elif kind == "startup_error": self._set_status(f"启动检查失败：{payload}", error=True)
                elif kind == "job":
                    job = payload; self._render_tasks()
                    if job.state == JobState.RUNNING: self.progress.set(job.progress); self._set_status(f"{job.stage}")
                    elif job.state == JobState.FAILED: self.progress.set(0); self._set_status(job.error, error=True)
                    elif job.state == JobState.COMPLETED:
                        self.progress.set(1); self._set_status(job.stage); self._load_gallery(); self._show_latest(job)
                elif kind == "gallery": self._render_gallery(payload)
                elif kind == "gallery_error": self._set_status(str(payload), error=True)
                elif kind == "image": self._display_image(payload)
                elif kind == "thumbnail": self._display_thumbnail(*payload)
        except queue.Empty: pass
        self.after(100, self._process_events)

    def _render_tasks(self) -> None:
        for widget in self.tasks_frame.winfo_children(): widget.destroy()
        if not self.manager: return
        queued = [job.id for job in self.manager.jobs() if job.state == JobState.QUEUED]
        for row, job in enumerate(self.manager.jobs()):
            card = ctk.CTkFrame(self.tasks_frame); card.grid(row=row, column=0, padx=6, pady=5, sticky="ew"); card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=f"{job.state.value} · {job.stage}", anchor="w").grid(row=0, column=0, padx=10, pady=(7, 0), sticky="ew")
            ctk.CTkLabel(card, text=job.options.description[:70] or "手动正向提示词", text_color="gray", anchor="w").grid(row=1, column=0, padx=10, pady=(0, 7), sticky="ew")
            if job.state in (JobState.QUEUED, JobState.SUBMITTING, JobState.RUNNING): ctk.CTkButton(card, text="取消", width=60, command=lambda j=job: self.manager.cancel(j.id)).grid(row=0, column=1, rowspan=2, padx=8)
            if job.state in (JobState.FAILED, JobState.CANCELLED): ctk.CTkButton(card, text="重试", width=60, command=lambda j=job: self.manager.retry(j.id)).grid(row=0, column=1, rowspan=2, padx=8)
            if job.state == JobState.QUEUED:
                index = queued.index(job.id)
                if index: ctk.CTkButton(card, text="↑", width=28, command=lambda i=index: self._move_queue(queued, i, -1)).grid(row=0, column=2, rowspan=2, padx=(0, 4))
                if index < len(queued)-1: ctk.CTkButton(card, text="↓", width=28, command=lambda i=index: self._move_queue(queued, i, 1)).grid(row=0, column=3, rowspan=2, padx=(0, 4))

    def _move_queue(self, ids, index, direction) -> None:
        ids[index], ids[index + direction] = ids[index + direction], ids[index]
        try: self.manager.reorder(ids); self._render_tasks()
        except ValueError as exc: self._set_status(str(exc), error=True)

    def _load_gallery(self) -> None:
        if not self.gallery or self._gallery_loaded: return
        self._gallery_loaded = True
        def worker():
            try: self.events.put(("gallery", self.gallery.list_items()))
            except Exception as exc: self.events.put(("gallery_error", exc))
        threading.Thread(target=worker, daemon=True).start()

    def _render_gallery(self, items: list[GalleryItem]) -> None:
        self._gallery_loaded = False; self.gallery_items = {item.id: item for item in items}
        self.thumbnail_buttons = {}
        for widget in self.gallery_frame.winfo_children(): widget.destroy()
        if not items: ctk.CTkLabel(self.gallery_frame, text="图库为空；生成的作品会加密保存于此。", text_color="gray").grid(row=0, column=0, padx=20, pady=20); return
        for index, item in enumerate(items[:80]):
            card = ctk.CTkFrame(self.gallery_frame); card.grid(row=index // 3, column=index % 3, padx=6, pady=6)
            preview = ctk.CTkButton(card, text="加载缩略图…", width=150, height=125, command=lambda i=item.id: self._open_gallery_item(i))
            preview.pack(padx=8, pady=(8, 3)); self.thumbnail_buttons[item.id] = preview
            ctk.CTkButton(card, text="导出", width=130, fg_color="transparent", command=lambda i=item.id: self._export(i)).pack(padx=8, pady=3)
            ctk.CTkButton(card, text="复制参数", width=130, fg_color="transparent", command=lambda i=item.id: self._copy_parameters(i)).pack(padx=8, pady=3)
            ctk.CTkButton(card, text="复用参数", width=130, fg_color="transparent", command=lambda i=item.id: self._reuse(i)).pack(padx=8, pady=(3, 8))
        self._load_thumbnails(items[:80])

    def _load_thumbnails(self, items: list[GalleryItem]) -> None:
        def worker():
            for item in items:
                try:
                    image = Image.open(io.BytesIO(self.gallery.image_bytes(item.id))); image.thumbnail((150, 120))
                    data = io.BytesIO(); image.save(data, format="PNG")
                    self.events.put(("thumbnail", (item.id, data.getvalue())))
                except Exception:
                    continue
        threading.Thread(target=worker, daemon=True).start()

    def _display_thumbnail(self, item_id: str, data: bytes) -> None:
        button = self.thumbnail_buttons.get(item_id)
        if not button or not button.winfo_exists(): return
        try:
            image = Image.open(io.BytesIO(data)); view = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            button.configure(image=view, text=""); button._image_ref = view
        except Exception: pass

    def _open_gallery_item(self, item_id: str) -> None:
        def worker():
            try: self.events.put(("image", self.gallery.image_bytes(item_id)))
            except Exception as exc: self.events.put(("gallery_error", exc))
        threading.Thread(target=worker, daemon=True).start()

    def _show_latest(self, job: Job) -> None:
        if job.gallery_ids: self._open_gallery_item(job.gallery_ids[-1])

    def _display_image(self, data: bytes) -> None:
        try:
            image = Image.open(io.BytesIO(data)); image.thumbnail((880, 680)); view = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            self.preview.configure(image=view, text=""); self.preview._image_ref = view; self.tabs.set("当前作品")
        except Exception as exc: self._set_status(f"图片显示失败：{exc}", error=True)

    def _export(self, item_id: str) -> None:
        target = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG 图像", "*.png"), ("所有文件", "*.*")])
        if not target: return
        try: self.gallery.export(item_id, target); self._set_status("已导出明文副本；加密原件仍保留在图库。")
        except Exception as exc: self._set_status(f"导出失败：{exc}", error=True)

    def _reuse(self, item_id: str) -> None:
        values = self.gallery_items[item_id].metadata.get("options", {})
        self.description.delete("1.0", "end"); self.description.insert("1.0", values.get("description", ""))
        self.quality_var.set("自定义"); self.random_seed.set(False); self._seed_toggle(); self.seed.delete(0, "end"); self.seed.insert(0, str(values.get("seed", 0)))
        self.positive.delete("1.0", "end"); self.positive.insert("1.0", values.get("positive_prompt", "")); self.negative.delete("1.0", "end"); self.negative.insert("1.0", values.get("negative_prompt", ""))
        self.model_var.set(values.get("checkpoint", self.model_var.get())); self.size_var.set(f"{values.get('width', 720)} × {values.get('height', 1280)}")
        self.count_var.set("1")
        for entry, name in ((self.s1_steps, "stage1_steps"), (self.s1_cfg, "stage1_cfg"), (self.s1_sampler, "stage1_sampler"), (self.s2_steps, "stage2_steps"), (self.s2_cfg, "stage2_cfg"), (self.s2_sampler, "stage2_sampler"), (self.upscale_model, "upscale_model"), (self.upscale_scale, "upscale_scale")):
            entry.delete(0, "end"); entry.insert(0, str(values.get(name, entry.get())))
        self.tabs.set("当前作品"); self._set_status("已载入作品参数；点击“加入生成队列”即可复现。")

    def _copy_parameters(self, item_id: str) -> None:
        self.clipboard_clear(); self.clipboard_append(json.dumps(self.gallery_items[item_id].metadata.get("options", {}), ensure_ascii=False, indent=2))
        self._set_status("生成参数已复制到剪贴板。")

    def _open_settings(self) -> None:
        dialog = ctk.CTkToplevel(self); dialog.title("设置"); dialog.geometry("560x280"); dialog.grab_set(); dialog.grid_columnconfigure(1, weight=1)
        fields = [("ComfyUI 地址", "server_address"), ("工作流 API JSON", "workflow_path"), ("加密图库目录", "gallery_dir")]; entries = {}
        for row, (label, name) in enumerate(fields):
            ctk.CTkLabel(dialog, text=label).grid(row=row, column=0, padx=14, pady=14, sticky="w")
            entry = ctk.CTkEntry(dialog); entry.insert(0, getattr(self.settings, name)); entry.grid(row=row, column=1, padx=14, pady=14, sticky="ew"); entries[name] = entry
        def save():
            self.settings = Settings(entries["server_address"].get().strip(), entries["workflow_path"].get().strip(), entries["gallery_dir"].get().strip(), self.model_var.get())
            self.store.save(self.settings); dialog.destroy(); self._set_status("设置已保存；重启应用后会重新检查连接与图库。")
        ctk.CTkButton(dialog, text="保存", command=save).grid(row=4, column=1, padx=14, pady=20, sticky="e")

    def _set_status(self, text: str, error: bool = False) -> None: self.status.configure(text=text, text_color="#ff6b6b" if error else "#dce4ee")
    def _close(self) -> None:
        if self.manager: self.manager.close()
        self.destroy()


def launch(project_root: Path) -> None:
    try: app = WorkbenchApp(project_root); app.mainloop()
    except KeyProtectionError as exc: messagebox.showerror("无法启动图库", str(exc))
