import os
import io
import time
import queue
import threading
import subprocess
import customtkinter as ctk
from PIL import Image

from ui.theme import Theme
from ui.prompt_library_modal import PromptLibraryModal
from ui.image_preview_modal import ImagePreviewModal
from ui.gallery_card import GalleryCard
from core.config import OUTPUT_DIR, ensure_dirs
from core.client import execute_generation_task, decrypt_image_data

class ComfyUIApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # 初始化目录与主题
        ensure_dirs()
        Theme.apply_global_settings()

        self.title("ComfyUI Studio 🎨")
        self.geometry("1180x780")
        self.minsize(980, 680)
        self.configure(fg_color=Theme.BG_ROOT)

        # 布局配置
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 状态与通信队列
        self.msg_queue = queue.Queue()
        self.task_queue = queue.Queue()
        self.is_generating = False
        
        # 当前加载的图片与其元信息
        self.current_image_bytes = None
        self.current_image_meta = {}
        self.current_image_path = None

        self._build_sidebar()
        self._build_main_area()

        # 启动 UI 消息监听定时器
        self.after(100, self.process_queue)

        # 延迟载入画廊缩略图
        self.after(500, self.load_gallery_thread)

    # ================= UI 结构构建 =================

    def _build_sidebar(self):
        """构建左侧控制控制台"""
        self.sidebar_frame = ctk.CTkFrame(
            self, 
            width=340, 
            corner_radius=0, 
            fg_color=Theme.BG_SIDEBAR,
            border_width=1,
            border_color=Theme.BORDER_SUBTLE
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)

        # 1. 顶部 Brand Logo
        brand_box = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        brand_box.pack(fill="x", padx=20, pady=(24, 16))

        logo_title = ctk.CTkLabel(
            brand_box, 
            text="✨ ComfyUI Studio", 
            font=Theme.font_title(),
            text_color=Theme.TEXT_PRIMARY
        )
        logo_title.pack(anchor="w")

        logo_sub = ctk.CTkLabel(
            brand_box, 
            text="Next-Gen AI Creative Workspace", 
            font=Theme.font_caption(),
            text_color=Theme.ACCENT_CYAN
        )
        logo_sub.pack(anchor="w", pady=(2, 0))

        # 2. 提示词输入区 Header
        prompt_header = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        prompt_header.pack(fill="x", padx=20, pady=(10, 6))

        prompt_label = ctk.CTkLabel(
            prompt_header, 
            text="画面描述 (Prompt)", 
            font=Theme.font_body_bold(),
            text_color=Theme.TEXT_PRIMARY
        )
        prompt_label.pack(side="left")

        # 提示词库快捷按钮
        self.repo_btn = ctk.CTkButton(
            prompt_header,
            text="📚 词库",
            font=Theme.font_caption(),
            width=65,
            height=26,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            corner_radius=Theme.RADIUS_SM,
            command=self.open_prompt_library
        )
        self.repo_btn.pack(side="right", padx=(4, 0))

        # 清空按钮
        clear_btn = ctk.CTkButton(
            prompt_header,
            text="🧹",
            width=28,
            height=26,
            fg_color="transparent",
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_MUTED,
            corner_radius=Theme.RADIUS_SM,
            command=self.clear_prompt_input
        )
        clear_btn.pack(side="right")

        # 3. 提示词多行文本框
        self.prompt_textbox = ctk.CTkTextbox(
            self.sidebar_frame, 
            height=160, 
            font=Theme.font_body(),
            fg_color=Theme.BG_INPUT,
            border_width=1,
            border_color=Theme.BORDER_DEFAULT,
            corner_radius=Theme.RADIUS_SM,
            text_color=Theme.TEXT_PRIMARY
        )
        self.prompt_textbox.pack(fill="x", padx=20, pady=(0, 16))

        # 4. 生成参数区（数量选择）
        options_card = ctk.CTkFrame(
            self.sidebar_frame, 
            fg_color=Theme.BG_CARD, 
            border_width=1,
            border_color=Theme.BORDER_DEFAULT,
            corner_radius=Theme.RADIUS_SM
        )
        options_card.pack(fill="x", padx=20, pady=(0, 16))

        opt_inner = ctk.CTkFrame(options_card, fg_color="transparent")
        opt_inner.pack(fill="x", padx=12, pady=10)

        count_label = ctk.CTkLabel(
            opt_inner, 
            text="生成张数", 
            font=Theme.font_body(),
            text_color=Theme.TEXT_SECONDARY
        )
        count_label.pack(side="left")

        self.count_var = ctk.StringVar(value="1张")
        self.count_menu = ctk.CTkOptionMenu(
            opt_inner, 
            values=["1张", "2张", "3张", "4张", "5张", "10张"],
            variable=self.count_var,
            width=95,
            height=30,
            fg_color=Theme.BG_INPUT,
            button_color=Theme.SECONDARY_BTN,
            button_hover_color=Theme.SECONDARY_BTN_HOVER,
            corner_radius=Theme.RADIUS_SM
        )
        self.count_menu.pack(side="right")

        # 5. 核心生成按钮
        self.generate_button = ctk.CTkButton(
            self.sidebar_frame, 
            text="🚀 开始生成", 
            command=self.start_generation, 
            height=46, 
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            corner_radius=Theme.RADIUS_MD
        )
        self.generate_button.pack(fill="x", padx=20, pady=(0, 20))

        # 6. 底部状态与进度区
        status_box = ctk.CTkFrame(
            self.sidebar_frame, 
            fg_color=Theme.BG_CARD,
            border_width=1,
            border_color=Theme.BORDER_DEFAULT,
            corner_radius=Theme.RADIUS_MD
        )
        status_box.pack(fill="x", side="bottom", padx=20, pady=20)

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(
            status_box, 
            height=8,
            fg_color=Theme.BG_INPUT,
            progress_color=Theme.PRIMARY,
            corner_radius=Theme.RADIUS_FULL
        )
        self.progress_bar.pack(fill="x", padx=14, pady=(14, 8))
        self.progress_bar.set(0)

        # 状态文本指示器
        self.status_label = ctk.CTkLabel(
            status_box, 
            text="就绪，等待下发任务", 
            font=Theme.font_caption(), 
            text_color=Theme.TEXT_MUTED, 
            justify="left", 
            wraplength=270,
            anchor="w"
        )
        self.status_label.pack(fill="x", padx=14, pady=(0, 14))

    def _build_main_area(self):
        """构建右侧核心展示区"""
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=Theme.BG_ROOT,
            segmented_button_fg_color=Theme.BG_SIDEBAR,
            segmented_button_selected_color=Theme.PRIMARY,
            segmented_button_selected_hover_color=Theme.PRIMARY_HOVER,
            segmented_button_unselected_color=Theme.BG_CARD,
            segmented_button_unselected_hover_color=Theme.BG_CARD_HOVER,
            corner_radius=Theme.RADIUS_MD
        )
        self.tabview.grid(row=0, column=1, padx=20, pady=(10, 20), sticky="nsew")

        self.tab_current = self.tabview.add("🖼️ 当前画布")
        self.tab_gallery = self.tabview.add("🏛️ 历史画廊")

        self._build_current_tab()
        self._build_gallery_tab()

    def _build_current_tab(self):
        """构建【当前画布】Tab"""
        self.tab_current.grid_rowconfigure(0, weight=1)
        self.tab_current.grid_columnconfigure(0, weight=1)

        # 图像显示卡片容器
        img_container = ctk.CTkFrame(
            self.tab_current,
            fg_color=Theme.BG_CARD_ALT,
            border_width=1,
            border_color=Theme.BORDER_SUBTLE,
            corner_radius=Theme.RADIUS_MD
        )
        img_container.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 10))
        img_container.grid_rowconfigure(0, weight=1)
        img_container.grid_columnconfigure(0, weight=1)

        self.image_label = ctk.CTkLabel(
            img_container, 
            text="✨ 暂无生成图像\n在左侧输入画面描述并点击【开始生成】", 
            font=Theme.font_subtitle(), 
            text_color=Theme.TEXT_MUTED,
            cursor="hand2"
        )
        self.image_label.grid(row=0, column=0, sticky="nsew")
        self.image_label.bind("<Button-1>", lambda e: self.open_current_in_lightbox())

        # 底部生成信息详情卡片
        self.meta_card = ctk.CTkFrame(
            self.tab_current,
            fg_color=Theme.BG_CARD,
            border_width=1,
            border_color=Theme.BORDER_DEFAULT,
            corner_radius=Theme.RADIUS_SM,
            height=44
        )
        self.meta_card.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
        self.meta_card.pack_propagate(False)

        self.meta_info_lbl = ctk.CTkLabel(
            self.meta_card,
            text="💡 提示: 生成完成后支持直接点击大图进入全屏沉浸预览",
            font=Theme.font_caption(),
            text_color=Theme.TEXT_MUTED
        )
        self.meta_info_lbl.pack(side="left", padx=16, pady=8)

        # 快速放大按钮
        self.meta_zoom_btn = ctk.CTkButton(
            self.meta_card,
            text="🔍 高清全屏预览",
            font=Theme.font_caption(),
            width=110,
            height=28,
            fg_color=Theme.SECONDARY_BTN,
            hover_color=Theme.SECONDARY_BTN_HOVER,
            corner_radius=Theme.RADIUS_SM,
            state="disabled",
            command=self.open_current_in_lightbox
        )
        self.meta_zoom_btn.pack(side="right", padx=12, pady=8)

    def _build_gallery_tab(self):
        """构建【历史画廊】Tab"""
        self.tab_gallery.grid_rowconfigure(1, weight=1)
        self.tab_gallery.grid_columnconfigure(0, weight=1)

        # 顶部工具栏
        gallery_toolbar = ctk.CTkFrame(self.tab_gallery, fg_color="transparent", height=40)
        gallery_toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(6, 8))

        self.refresh_btn = ctk.CTkButton(
            gallery_toolbar, 
            text="🔄 刷新画廊", 
            font=Theme.font_caption(),
            width=90,
            height=30,
            fg_color=Theme.SECONDARY_BTN,
            hover_color=Theme.SECONDARY_BTN_HOVER,
            corner_radius=Theme.RADIUS_SM,
            command=self.load_gallery_thread
        )
        self.refresh_btn.pack(side="left", padx=(0, 8))

        open_folder_btn = ctk.CTkButton(
            gallery_toolbar,
            text="📁 打开输出目录",
            font=Theme.font_caption(),
            width=100,
            height=30,
            fg_color=Theme.SECONDARY_BTN,
            hover_color=Theme.SECONDARY_BTN_HOVER,
            corner_radius=Theme.RADIUS_SM,
            command=self.open_output_folder
        )
        open_folder_btn.pack(side="left")

        self.gallery_count_lbl = ctk.CTkLabel(
            gallery_toolbar,
            text="",
            font=Theme.font_caption(),
            text_color=Theme.TEXT_MUTED
        )
        self.gallery_count_lbl.pack(side="right", padx=10)

        # 滚动展示区域
        self.gallery_scroll = ctk.CTkScrollableFrame(
            self.tab_gallery,
            fg_color=Theme.BG_ROOT,
            corner_radius=Theme.RADIUS_SM
        )
        self.gallery_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.gallery_scroll.grid_columnconfigure((0, 1, 2), weight=1)

    # ================= 提示词库交互 =================

    def open_prompt_library(self):
        """唤起提示词存储库弹窗面板"""
        PromptLibraryModal(
            self,
            on_append_prompt=self.append_prompt,
            on_replace_prompt=self.replace_prompt,
            get_current_prompt_func=lambda: self.prompt_textbox.get("0.0", "end")
        )

    def append_prompt(self, text):
        current = self.prompt_textbox.get("0.0", "end").strip()
        if current:
            new_text = current + ", " + text.strip()
        else:
            new_text = text.strip()
        self.prompt_textbox.delete("0.0", "end")
        self.prompt_textbox.insert("0.0", new_text)

    def replace_prompt(self, text):
        self.prompt_textbox.delete("0.0", "end")
        self.prompt_textbox.insert("0.0", text.strip())

    def clear_prompt_input(self):
        self.prompt_textbox.delete("0.0", "end")

    # ================= 图像展示与全屏 Lightbox =================

    def display_image(self, image_bytes, metadata=None, filepath=None):
        """在当前画布中高清适配展示图像并更新元信息卡片"""
        try:
            self.current_image_bytes = image_bytes
            self.current_image_meta = metadata or {}
            self.current_image_path = filepath

            image = Image.open(io.BytesIO(image_bytes))
            w, h = image.size

            # DPI 适配
            try:
                scaling = self._get_window_scaling()
            except AttributeError:
                scaling = 1.0

            logical_w = self.winfo_width() / scaling
            logical_h = self.winfo_height() / scaling

            if logical_w < 100 or logical_h < 100:
                logical_w, logical_h = 1100, 750

            # 可用视口计算
            frame_w = max(200, logical_w - 410)
            frame_h = max(200, logical_h - 170)

            ratio = min(frame_w / w, frame_h / h)
            new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))

            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=new_size)
            self.image_label.configure(image=ctk_image, text="")
            self.image_label._image_ref = ctk_image

            # 更新底部元信息卡片
            info_parts = [f"📐 分辨率: {w} × {h}"]
            if "elapsed" in self.current_image_meta:
                info_parts.append(f"⏱️ 耗时: {self.current_image_meta['elapsed']}s")
            if "timestamp" in self.current_image_meta:
                info_parts.append(f"🕒 时间: {self.current_image_meta['timestamp']}")
            if filepath:
                info_parts.append("🔐 加密存储")

            self.meta_info_lbl.configure(
                text="  |  ".join(info_parts),
                text_color=Theme.TEXT_SECONDARY
            )
            self.meta_zoom_btn.configure(state="normal")

        except Exception as e:
            self.msg_queue.put(("error", f"渲染图片失败: {e}"))

    def open_current_in_lightbox(self):
        """进入高清全屏 Lightbox 预览"""
        if self.current_image_bytes:
            ImagePreviewModal(
                self,
                self.current_image_bytes,
                title="ComfyUI 高清大图预览",
                filepath=self.current_image_path,
                metadata=self.current_image_meta
            )

    def preview_historical_image(self, path):
        """画廊卡片点击唤起 Lightbox 预览"""
        try:
            with open(path, "rb") as f:
                raw_bytes = f.read()
            img_data = decrypt_image_data(raw_bytes)
            ImagePreviewModal(
                self,
                img_data,
                title=f"画廊预览 - {os.path.basename(path)}",
                filepath=path
            )
        except Exception as e:
            self.msg_queue.put(("error", f"打开历史大图失败: {e}"))

    def view_historical_image(self, path):
        """将选中的历史图片载入【当前画布】并切换视窗"""
        try:
            with open(path, "rb") as f:
                raw_bytes = f.read()
            image_data = decrypt_image_data(raw_bytes)

            try:
                pil_img = Image.open(io.BytesIO(image_data))
                w, h = pil_img.size
            except Exception:
                w, h = 0, 0

            meta = {
                "width": w,
                "height": h,
                "timestamp": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
            }

            self.tabview.set("🖼️ 当前画布")
            self.display_image(image_data, metadata=meta, filepath=path)
        except Exception as e:
            self.msg_queue.put(("error", f"载入历史图片失败: {e}"))

    def open_output_folder(self):
        """打开输出存储目录"""
        if os.path.exists(OUTPUT_DIR):
            subprocess.run(["explorer", os.path.normpath(OUTPUT_DIR)])

    # ================= 历史画廊加载逻辑 =================

    def load_gallery_thread(self):
        self.refresh_btn.configure(state="disabled", text="⏳ 加载中...")
        threading.Thread(target=self._load_gallery_worker, daemon=True).start()

    def _load_gallery_worker(self):
        self.msg_queue.put(("gallery_clear", None))

        if not os.path.exists(OUTPUT_DIR):
            self.msg_queue.put(("gallery_done", 0))
            return

        images = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(('.png', '.jpg', '.jpeg', '.enc'))]
        images.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)), reverse=True)
        total_count = len(images)
        images = images[:36]  # 限制展示前 36 张以保证丝滑流畅

        for img_name in images:
            img_path = os.path.join(OUTPUT_DIR, img_name)
            try:
                with open(img_path, "rb") as f:
                    raw_data = f.read()

                image_data = decrypt_image_data(raw_data)
                img = Image.open(io.BytesIO(image_data))
                img.thumbnail((220, 220))

                thumb_io = io.BytesIO()
                img.save(thumb_io, format="PNG")

                self.msg_queue.put(("gallery_item", (img_path, img_name, img.size, thumb_io.getvalue())))
            except Exception as e:
                print(f"载入缩略图异常 {img_name}: {e}")

        self.msg_queue.put(("gallery_done", total_count))

    # ================= 任务生成流程调度 =================

    def start_generation(self):
        user_prompt = self.prompt_textbox.get("0.0", "end").strip()
        if not user_prompt:
            self.status_label.configure(text="⚠️ 请输入画面描述", text_color=Theme.WARNING)
            return

        count_str = self.count_var.get().replace("张", "")
        try:
            count = int(count_str)
        except ValueError:
            count = 1

        for _ in range(count):
            self.task_queue.put(user_prompt)

        if self.is_generating:
            self.msg_queue.put(("update_queue_status", ""))
        else:
            self.is_generating = True
            self.msg_queue.put(("update_queue_status", ""))
            self.msg_queue.put(("status", "准备派发生成任务..."))
            threading.Thread(target=self.job_worker_thread, daemon=True).start()

    def job_worker_thread(self):
        while not self.task_queue.empty():
            current_prompt = self.task_queue.get()
            self.msg_queue.put(("update_queue_status", ""))
            self.msg_queue.put(("progress", 0))

            try:
                execute_generation_task(current_prompt, self.msg_queue)
            except Exception:
                # 异常信息已通过 msg_queue 上报
                pass
            finally:
                self.task_queue.task_done()
                self.msg_queue.put(("done", ""))

        self.msg_queue.put(("all_done", ""))

    # ================= 消息队列消费主循环 =================

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()

                if msg_type == "status":
                    self.status_label.configure(text=str(data), text_color=Theme.TEXT_SECONDARY)
                elif msg_type == "progress":
                    self.progress_bar.set(data)
                elif msg_type == "image":
                    img_bytes, meta = data
                    self.tabview.set("🖼️ 当前画布")
                    self.display_image(img_bytes, metadata=meta, filepath=meta.get("saved_path"))
                    # 异步刷新画廊
                    self.load_gallery_thread()
                elif msg_type == "done":
                    self.progress_bar.set(1.0)
                elif msg_type == "all_done":
                    self.is_generating = False
                    self.generate_button.configure(text="🚀 开始生成", state="normal")
                    self.progress_bar.set(1.0)
                elif msg_type == "update_queue_status":
                    q_size = self.task_queue.qsize()
                    if q_size > 0:
                        self.generate_button.configure(text=f"🚀 追加排队 (排队: {q_size})")
                    else:
                        self.generate_button.configure(text="⏳ 正在绘制中...")
                elif msg_type == "error":
                    self.status_label.configure(text=f"❌ {data}", text_color=Theme.ERROR)
                    self.progress_bar.set(0)
                elif msg_type == "gallery_clear":
                    for w in self.gallery_scroll.winfo_children():
                        w.destroy()
                    self.g_row, self.g_col = 0, 0
                elif msg_type == "gallery_item":
                    img_path, img_name, img_size, img_data = data
                    try:
                        pil_thumb = Image.open(io.BytesIO(img_data))
                        ctk_thumb = ctk.CTkImage(light_image=pil_thumb, dark_image=pil_thumb, size=img_size)

                        card = GalleryCard(
                            self.gallery_scroll,
                            image_path=img_path,
                            image_name=img_name,
                            thumbnail_data=ctk_thumb,
                            on_select=self.view_historical_image,
                            on_preview_large=self.preview_historical_image
                        )
                        card.grid(row=self.g_row, column=self.g_col, padx=8, pady=8, sticky="ew")

                        self.g_col += 1
                        if self.g_col >= 3:
                            self.g_col = 0
                            self.g_row += 1
                    except Exception as e:
                        print(f"渲染画廊卡片错误: {e}")
                elif msg_type == "gallery_done":
                    self.refresh_btn.configure(state="normal", text="🔄 刷新画廊")
                    count = data or 0
                    self.gallery_count_lbl.configure(text=f"本地共 {count} 张记录")

        except queue.Empty:
            pass

        # 持续循环轮询 (100ms)
        self.after(100, self.process_queue)
