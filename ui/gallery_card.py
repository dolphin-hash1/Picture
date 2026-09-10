import os
import subprocess
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image
from ui.theme import Theme

class GalleryCard(ctk.CTkFrame):
    """
    画廊独立圆角卡片微组件
    包含缩略图展示、悬停高亮动效、快捷预览、定位文件与删除管理
    """
    def __init__(self, master, image_path, image_name, thumbnail_data, on_select=None, on_preview_large=None, on_delete=None):
        super().__init__(
            master,
            fg_color=Theme.BG_CARD,
            border_width=1,
            border_color=Theme.BORDER_DEFAULT,
            corner_radius=Theme.RADIUS_MD
        )
        self.image_path = image_path
        self.image_name = image_name
        self.thumbnail_data = thumbnail_data
        self.on_select = on_select
        self.on_preview_large = on_preview_large
        self.on_delete = on_delete

        self._build_ui()
        self._bind_hover_effects(self)

    def _build_ui(self):
        # 顶部图片缩略图展示区
        self.thumb_container = ctk.CTkFrame(self, fg_color="#101116", corner_radius=Theme.RADIUS_SM)
        self.thumb_container.pack(fill="both", expand=True, padx=8, pady=8)

        # 缩略图按钮（单击载入主视窗）
        self.img_btn = ctk.CTkButton(
            self.thumb_container,
            image=self.thumbnail_data,
            text="",
            fg_color="transparent",
            hover_color="#1F222E",
            corner_radius=Theme.RADIUS_SM,
            command=self._handle_click
        )
        self.img_btn.pack(padx=2, pady=2)
        self.img_btn.bind("<Double-Button-1>", lambda e: self._handle_large_preview())

        # 底部信息与动作栏
        footer = ctk.CTkFrame(self, fg_color="transparent", height=32)
        footer.pack(fill="x", padx=8, pady=(0, 6))

        # 文件名/时间文字
        short_name = self.image_name
        if len(short_name) > 14:
            short_name = short_name[:12] + "…"

        name_lbl = ctk.CTkLabel(
            footer,
            text=short_name,
            font=Theme.font_caption(),
            text_color=Theme.TEXT_SECONDARY
        )
        name_lbl.pack(side="left", padx=2)

        # 右侧微操作按钮集
        # 1. 🗑️ 删除
        del_btn = ctk.CTkButton(
            footer,
            text="🗑️",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=Theme.DANGER_BTN_HOVER,
            text_color=Theme.ERROR,
            corner_radius=Theme.RADIUS_SM,
            command=self._handle_delete
        )
        del_btn.pack(side="right", padx=1)

        # 2. 📂 定位文件
        loc_btn = ctk.CTkButton(
            footer,
            text="📂",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_MUTED,
            corner_radius=Theme.RADIUS_SM,
            command=self._locate_file
        )
        loc_btn.pack(side="right", padx=1)

        # 3. 🔍 放大预览 (Lightbox)
        zoom_btn = ctk.CTkButton(
            footer,
            text="🔍",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_MUTED,
            corner_radius=Theme.RADIUS_SM,
            command=self._handle_large_preview
        )
        zoom_btn.pack(side="right", padx=1)

    def _bind_hover_effects(self, widget):
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        for child in widget.winfo_children():
            # 按钮本身有自带的 hover 逻辑，不干扰
            if not isinstance(child, ctk.CTkButton):
                child.bind("<Enter>", self._on_enter)
                child.bind("<Leave>", self._on_leave)

    def _on_enter(self, event=None):
        self.configure(border_color=Theme.PRIMARY, fg_color=Theme.BG_CARD_HOVER)

    def _on_leave(self, event=None):
        self.configure(border_color=Theme.BORDER_DEFAULT, fg_color=Theme.BG_CARD)

    def _handle_click(self):
        if self.on_select:
            self.on_select(self.image_path)

    def _handle_large_preview(self):
        if self.on_preview_large:
            self.on_preview_large(self.image_path)

    def _locate_file(self):
        if os.path.exists(self.image_path):
            norm_path = os.path.normpath(self.image_path)
            subprocess.run(["explorer", "/select,", norm_path])

    def _handle_delete(self):
        confirm = messagebox.askyesno("删除确认", f"确定要从磁盘删除该文件吗？\n{os.path.basename(self.image_path)}")
        if confirm:
            try:
                if os.path.exists(self.image_path):
                    os.remove(self.image_path)
                if self.on_delete:
                    self.on_delete(self)
                else:
                    self.destroy()
            except Exception as e:
                messagebox.showerror("删除失败", f"无法删除文件: {e}")
