import io
import os
import subprocess
import customtkinter as ctk
from PIL import Image
from ui.theme import Theme

class ImagePreviewModal(ctk.CTkToplevel):
    """
    大图高清预览/沉浸式 Lightbox 弹窗
    支持自适应缩放、ESC 快速退出、展示元信息与文件操作
    """
    def __init__(self, master, image_bytes, title="高清大图预览", filepath=None, metadata=None):
        super().__init__(master)
        self.master_window = master
        self.image_bytes = image_bytes
        self.image_filepath = filepath
        self.metadata = metadata or {}

        self.title(title)
        self.geometry("960x760")
        self.minsize(500, 400)
        self.configure(fg_color="#08090C")

        self.transient(master)
        self.grab_set()

        self.pil_image = Image.open(io.BytesIO(image_bytes))
        self.orig_w, self.orig_h = self.pil_image.size

        self._build_ui()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Configure>", self._on_window_resize)

        # 居中显示
        self.after(50, self._center_window)

    def _center_window(self):
        self.update_idletasks()
        try:
            m_x = self.master_window.winfo_x()
            m_y = self.master_window.winfo_y()
            m_w = self.master_window.winfo_width()
            m_h = self.master_window.winfo_height()
            x = m_x + max(0, (m_w - 960) // 2)
            y = m_y + max(0, (m_h - 760) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self):
        # 顶部工具与信息条
        top_bar = ctk.CTkFrame(self, fg_color="#101117", height=46, corner_radius=0)
        top_bar.pack(fill="x", side="top")
        top_bar.pack_propagate(False)

        # 尺寸信息微标签
        info_str = f"📐 {self.orig_w} × {self.orig_h}"
        if "elapsed" in self.metadata:
            info_str += f" | ⚡ {self.metadata['elapsed']}s"
        info_lbl = ctk.CTkLabel(top_bar, text=info_str, font=Theme.font_caption(), text_color=Theme.TEXT_SECONDARY)
        info_lbl.pack(side="left", padx=16)

        # 右侧操作区：打开文件夹 + 关闭按钮
        close_btn = ctk.CTkButton(
            top_bar,
            text="✕",
            width=36,
            height=32,
            fg_color="transparent",
            hover_color=Theme.DANGER_BTN_HOVER,
            text_color=Theme.TEXT_PRIMARY,
            command=self.destroy
        )
        close_btn.pack(side="right", padx=10)

        if self.image_filepath and os.path.exists(self.image_filepath):
            locate_btn = ctk.CTkButton(
                top_bar,
                text="📂 打开文件位置",
                font=Theme.font_caption(),
                height=28,
                fg_color=Theme.SECONDARY_BTN,
                hover_color=Theme.SECONDARY_BTN_HOVER,
                text_color=Theme.TEXT_PRIMARY,
                command=self._locate_file
            )
            locate_btn.pack(side="right", padx=6)

        # 中部大图展示容器
        self.image_container = ctk.CTkFrame(self, fg_color="#08090C")
        self.image_container.pack(fill="both", expand=True, padx=10, pady=10)

        self.display_label = ctk.CTkLabel(self.image_container, text="")
        self.display_label.pack(expand=True)

        self._resize_timer = None

    def _locate_file(self):
        if self.image_filepath and os.path.exists(self.image_filepath):
            norm_path = os.path.normpath(self.image_filepath)
            subprocess.run(["explorer", "/select,", norm_path])

    def _on_window_resize(self, event):
        # 仅响应主容器本身的尺寸变动，防抖更新
        if event.widget == self:
            if self._resize_timer:
                self.after_cancel(self._resize_timer)
            self._resize_timer = self.after(80, self._render_image)

    def _render_image(self):
        try:
            avail_w = max(100, self.image_container.winfo_width() - 20)
            avail_h = max(100, self.image_container.winfo_height() - 20)

            ratio = min(avail_w / self.orig_w, avail_h / self.orig_h)
            new_w = max(1, int(self.orig_w * ratio))
            new_h = max(1, int(self.orig_h * ratio))

            ctk_img = ctk.CTkImage(light_image=self.pil_image, dark_image=self.pil_image, size=(new_w, new_h))
            self.display_label.configure(image=ctk_img)
            self.display_label._ref = ctk_img
        except Exception as e:
            print(f"渲染大图预览错误: {e}")
