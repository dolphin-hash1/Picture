import os
import json
import uuid
import time
import customtkinter as ctk
from tkinter import messagebox
from ui.theme import Theme
from core.config import PROMPTS_FILE

def load_prompt_library():
    """读取本地提示词库"""
    if not os.path.exists(PROMPTS_FILE):
        default_data = {
            "categories": ["我的收藏"],
            "prompts": []
        }
        save_prompt_library(default_data)
        return default_data
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "categories" not in data:
                data["categories"] = ["我的收藏"]
            if "prompts" not in data:
                data["prompts"] = []
            return data
    except Exception as e:
        print(f"读取提示词库失败: {e}")
        return {"categories": ["我的收藏"], "prompts": []}

def save_prompt_library(data):
    """保存提示词库至本地 JSON"""
    try:
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存提示词库失败: {e}")

class PromptLibraryModal(ctk.CTkToplevel):
    def __init__(self, master, on_append_prompt=None, on_replace_prompt=None, get_current_prompt_func=None):
        super().__init__(master)
        self.master_window = master
        self.on_append_prompt = on_append_prompt
        self.on_replace_prompt = on_replace_prompt
        self.get_current_prompt_func = get_current_prompt_func

        self.title("📚 提示词存储库")
        self.geometry("820x620")
        self.minsize(700, 500)
        self.configure(fg_color=Theme.BG_ROOT)

        # 确保窗口居中显示
        self.after(50, self._center_window)
        self.transient(master)
        self.grab_set()

        self.library_data = load_prompt_library()
        self.current_filter_category = "全部"
        self.search_query = ""

        self._build_ui()
        self._refresh_prompt_list()

    def _center_window(self):
        self.update_idletasks()
        try:
            m_x = self.master_window.winfo_x()
            m_y = self.master_window.winfo_y()
            m_w = self.master_window.winfo_width()
            m_h = self.master_window.winfo_height()
            x = m_x + max(0, (m_w - 820) // 2)
            y = m_y + max(0, (m_h - 620) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self):
        # 顶部标题栏
        top_bar = ctk.CTkFrame(self, fg_color=Theme.BG_SIDEBAR, corner_radius=0, height=65)
        top_bar.pack(fill="x", side="top")
        top_bar.pack_propagate(False)

        title_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_box.pack(side="left", padx=20, pady=12)

        title_lbl = ctk.CTkLabel(
            title_box, 
            text="📚 提示词存储库", 
            font=Theme.font_subtitle(), 
            text_color=Theme.TEXT_PRIMARY
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            title_box, 
            text="纯净沉淀您的画面灵感与常用风格组合", 
            font=Theme.font_caption(), 
            text_color=Theme.TEXT_MUTED
        )
        sub_lbl.pack(anchor="w")

        # 顶部右侧操作按钮区
        btn_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        btn_box.pack(side="right", padx=20)

        import_cur_btn = ctk.CTkButton(
            btn_box,
            text="📥 抓取当前输入框",
            font=Theme.font_caption(),
            fg_color=Theme.SECONDARY_BTN,
            hover_color=Theme.SECONDARY_BTN_HOVER,
            text_color=Theme.TEXT_PRIMARY,
            height=32,
            corner_radius=Theme.RADIUS_SM,
            command=self._quick_import_from_main
        )
        import_cur_btn.pack(side="left", padx=6)

        add_btn = ctk.CTkButton(
            btn_box,
            text="✨ 新增词条",
            font=Theme.font_body_bold(),
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_PRIMARY,
            height=32,
            corner_radius=Theme.RADIUS_SM,
            command=self._open_add_dialog
        )
        add_btn.pack(side="left", padx=6)

        # 过滤与搜索控制条
        ctrl_bar = ctk.CTkFrame(self, fg_color=Theme.BG_ROOT, height=48)
        ctrl_bar.pack(fill="x", padx=20, pady=(15, 8))

        # 分类下拉过滤
        self.cat_var = ctk.StringVar(value="全部分类")
        categories_options = ["全部分类"] + self.library_data.get("categories", ["我的收藏"])
        self.cat_menu = ctk.CTkOptionMenu(
            ctrl_bar,
            values=categories_options,
            variable=self.cat_var,
            width=130,
            height=32,
            corner_radius=Theme.RADIUS_SM,
            fg_color=Theme.BG_CARD,
            button_color=Theme.SECONDARY_BTN,
            button_hover_color=Theme.SECONDARY_BTN_HOVER,
            command=self._on_category_selected
        )
        self.cat_menu.pack(side="left", padx=(0, 10))

        # 分类管理小按钮
        manage_cat_btn = ctk.CTkButton(
            ctrl_bar,
            text="📁 分类管理",
            font=Theme.font_caption(),
            width=85,
            height=32,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BG_CARD_HOVER,
            border_width=1,
            border_color=Theme.BORDER_SUBTLE,
            corner_radius=Theme.RADIUS_SM,
            command=self._open_category_manager
        )
        manage_cat_btn.pack(side="left", padx=(0, 15))

        # 搜索框
        self.search_entry = ctk.CTkEntry(
            ctrl_bar,
            placeholder_text="🔍 搜索提示词或标题...",
            height=32,
            corner_radius=Theme.RADIUS_SM,
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BORDER_DEFAULT,
            text_color=Theme.TEXT_PRIMARY
        )
        self.search_entry.pack(side="right", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search_typing)

        # 核心滚动词卡列表
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=Theme.BG_ROOT,
            corner_radius=Theme.RADIUS_SM
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

    def _on_category_selected(self, choice):
        self.current_filter_category = choice
        self._refresh_prompt_list()

    def _on_search_typing(self, event=None):
        self.search_query = self.search_entry.get().strip().lower()
        self._refresh_prompt_list()

    def _refresh_prompt_list(self):
        # 清空原展示控件
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        prompts = self.library_data.get("prompts", [])

        # 过滤
        filtered = []
        for p in prompts:
            cat = p.get("category", "我的收藏")
            if self.current_filter_category not in ("全部分类", "全部") and cat != self.current_filter_category:
                continue
            if self.search_query:
                title = p.get("title", "").lower()
                content = p.get("prompt", "").lower()
                tags = " ".join(p.get("tags", [])).lower()
                if self.search_query not in title and self.search_query not in content and self.search_query not in tags:
                    continue
            filtered.append(p)

        if not filtered:
            empty_box = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            empty_box.pack(expand=True, pady=60)
            ctk.CTkLabel(
                empty_box,
                text="📭 暂无匹配的提示词条目",
                font=Theme.font_subtitle(),
                text_color=Theme.TEXT_MUTED
            ).pack(pady=4)
            ctk.CTkLabel(
                empty_box,
                text="点击上方【新增词条】或【抓取当前输入框】开始收藏您的提示词",
                font=Theme.font_caption(),
                text_color=Theme.TEXT_MUTED
            ).pack()
            return

        # 绘制卡片
        for item in filtered:
            self._render_prompt_card(item)

    def _render_prompt_card(self, item):
        card = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=Theme.BG_CARD,
            border_width=1,
            border_color=Theme.BORDER_DEFAULT,
            corner_radius=Theme.RADIUS_MD
        )
        card.pack(fill="x", pady=6, padx=4)

        # 顶部行：分类徽章 + 标题 + 时间
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=14, pady=(10, 4))

        cat_badge = ctk.CTkLabel(
            top_row,
            text=f"📁 {item.get('category', '我的收藏')}",
            font=Theme.font_caption(),
            fg_color=Theme.BG_INPUT,
            corner_radius=Theme.RADIUS_SM,
            text_color=Theme.ACCENT_CYAN,
            padx=8,
            pady=2
        )
        cat_badge.pack(side="left", padx=(0, 10))

        title_lbl = ctk.CTkLabel(
            top_row,
            text=item.get("title", "未命名提示词"),
            font=Theme.font_body_bold(),
            text_color=Theme.TEXT_PRIMARY
        )
        title_lbl.pack(side="left")

        time_lbl = ctk.CTkLabel(
            top_row,
            text=item.get("created_at", ""),
            font=Theme.font_caption(),
            text_color=Theme.TEXT_MUTED
        )
        time_lbl.pack(side="right")

        # 提示词内容框
        content_box = ctk.CTkFrame(card, fg_color=Theme.BG_INPUT, corner_radius=Theme.RADIUS_SM)
        content_box.pack(fill="x", padx=14, pady=4)

        prompt_text = item.get("prompt", "")
        preview_text = (prompt_text[:180] + "...") if len(prompt_text) > 180 else prompt_text

        content_lbl = ctk.CTkLabel(
            content_box,
            text=preview_text,
            font=Theme.font_body(),
            text_color=Theme.TEXT_SECONDARY,
            justify="left",
            wraplength=720,
            padx=10,
            pady=8
        )
        content_lbl.pack(fill="x", anchor="w")

        # 底部操作栏
        bottom_row = ctk.CTkFrame(card, fg_color="transparent")
        bottom_row.pack(fill="x", padx=14, pady=(6, 10))

        # 快速追加
        append_btn = ctk.CTkButton(
            bottom_row,
            text="➕ 追加到末尾",
            font=Theme.font_caption(),
            width=90,
            height=28,
            fg_color=Theme.SECONDARY_BTN,
            hover_color=Theme.SECONDARY_BTN_HOVER,
            corner_radius=Theme.RADIUS_SM,
            command=lambda p=prompt_text: self._action_append(p)
        )
        append_btn.pack(side="left", padx=(0, 8))

        # 覆盖输入框
        replace_btn = ctk.CTkButton(
            bottom_row,
            text="🔄 覆盖填入",
            font=Theme.font_caption(),
            width=80,
            height=28,
            fg_color=Theme.SECONDARY_BTN,
            hover_color=Theme.SECONDARY_BTN_HOVER,
            corner_radius=Theme.RADIUS_SM,
            command=lambda p=prompt_text: self._action_replace(p)
        )
        replace_btn.pack(side="left", padx=(0, 8))

        # 复制剪贴板
        copy_btn = ctk.CTkButton(
            bottom_row,
            text="📋 复制",
            font=Theme.font_caption(),
            width=65,
            height=28,
            fg_color="transparent",
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_SECONDARY,
            corner_radius=Theme.RADIUS_SM,
            command=lambda p=prompt_text: self._action_copy(p)
        )
        copy_btn.pack(side="left")

        # 右侧操作：编辑 & 删除
        del_btn = ctk.CTkButton(
            bottom_row,
            text="🗑️",
            width=32,
            height=28,
            fg_color="transparent",
            hover_color=Theme.DANGER_BTN_HOVER,
            text_color=Theme.ERROR,
            corner_radius=Theme.RADIUS_SM,
            command=lambda item_id=item.get("id"): self._action_delete(item_id)
        )
        del_btn.pack(side="right")

        edit_btn = ctk.CTkButton(
            bottom_row,
            text="✏️ 编辑",
            font=Theme.font_caption(),
            width=60,
            height=28,
            fg_color="transparent",
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_MUTED,
            corner_radius=Theme.RADIUS_SM,
            command=lambda it=item: self._open_edit_dialog(it)
        )
        edit_btn.pack(side="right", padx=6)

    def _action_append(self, prompt_text):
        if self.on_append_prompt:
            self.on_append_prompt(prompt_text)
            self._show_toast("已追加至输入框末尾")

    def _action_replace(self, prompt_text):
        if self.on_replace_prompt:
            self.on_replace_prompt(prompt_text)
            self._show_toast("已替换输入框内容")

    def _action_copy(self, prompt_text):
        self.clipboard_clear()
        self.clipboard_append(prompt_text)
        self._show_toast("已复制到剪贴板")

    def _action_delete(self, item_id):
        self.library_data["prompts"] = [p for p in self.library_data.get("prompts", []) if p.get("id") != item_id]
        save_prompt_library(self.library_data)
        self._refresh_prompt_list()

    def _show_toast(self, text):
        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)
        toast.configure(fg_color=Theme.PRIMARY)
        lbl = ctk.CTkLabel(toast, text=text, font=Theme.font_caption(), text_color="#FFFFFF", padx=12, pady=6)
        lbl.pack()
        toast.update_idletasks()
        
        x = self.winfo_x() + (self.winfo_width() - toast.winfo_width()) // 2
        y = self.winfo_y() + self.winfo_height() - 70
        toast.geometry(f"+{x}+{y}")
        self.after(1200, toast.destroy)

    def _quick_import_from_main(self):
        current_text = ""
        if self.get_current_prompt_func:
            current_text = self.get_current_prompt_func().strip()
        if not current_text:
            messagebox.showinfo("提示", "当前主界面输入框为空，无需抓取。")
            return
        
        self._open_add_dialog(initial_prompt=current_text)

    def _open_add_dialog(self, initial_prompt=""):
        self._open_item_editor(mode="add", initial_data={"prompt": initial_prompt})

    def _open_edit_dialog(self, item):
        self._open_item_editor(mode="edit", initial_data=item)

    def _open_item_editor(self, mode="add", initial_data=None):
        initial_data = initial_data or {}
        dialog = ctk.CTkToplevel(self)
        dialog.title("新增提示词" if mode == "add" else "编辑提示词")
        dialog.geometry("540x480")
        dialog.configure(fg_color=Theme.BG_ROOT)
        dialog.transient(self)
        dialog.grab_set()

        # 表单字段
        frm = ctk.CTkFrame(dialog, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(frm, text="标题 / 描述名称:", font=Theme.font_body_bold(), text_color=Theme.TEXT_PRIMARY).pack(anchor="w", pady=(0, 4))
        title_entry = ctk.CTkEntry(frm, fg_color=Theme.BG_INPUT, border_color=Theme.BORDER_DEFAULT, height=32)
        title_entry.pack(fill="x", pady=(0, 12))
        title_entry.insert(0, initial_data.get("title", ""))

        ctk.CTkLabel(frm, text="归属分类:", font=Theme.font_body_bold(), text_color=Theme.TEXT_PRIMARY).pack(anchor="w", pady=(0, 4))
        cats = self.library_data.get("categories", ["我的收藏"])
        cat_var = ctk.StringVar(value=initial_data.get("category", cats[0] if cats else "我的收藏"))
        cat_menu = ctk.CTkOptionMenu(frm, values=cats, variable=cat_var, fg_color=Theme.BG_CARD, height=32)
        cat_menu.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(frm, text="提示词正文 (Prompt):", font=Theme.font_body_bold(), text_color=Theme.TEXT_PRIMARY).pack(anchor="w", pady=(0, 4))
        prompt_box = ctk.CTkTextbox(frm, fg_color=Theme.BG_INPUT, border_width=1, border_color=Theme.BORDER_DEFAULT, height=180)
        prompt_box.pack(fill="both", expand=True, pady=(0, 16))
        prompt_box.insert("0.0", initial_data.get("prompt", ""))

        btn_row = ctk.CTkFrame(frm, fg_color="transparent")
        btn_row.pack(fill="x")

        def save_action():
            t = title_entry.get().strip() or "未命名词条"
            c = cat_var.get()
            p = prompt_box.get("0.0", "end").strip()
            if not p:
                messagebox.showwarning("警告", "提示词内容不能为空")
                return

            if mode == "add":
                new_item = {
                    "id": str(uuid.uuid4())[:8],
                    "title": t,
                    "category": c,
                    "prompt": p,
                    "created_at": time.strftime("%Y-%m-%d %H:%M")
                }
                self.library_data.setdefault("prompts", []).insert(0, new_item)
            else:
                for item in self.library_data.get("prompts", []):
                    if item.get("id") == initial_data.get("id"):
                        item["title"] = t
                        item["category"] = c
                        item["prompt"] = p
                        break

            save_prompt_library(self.library_data)
            self._refresh_prompt_list()
            dialog.destroy()

        save_btn = ctk.CTkButton(
            btn_row, 
            text="💾 保存", 
            fg_color=Theme.PRIMARY, 
            hover_color=Theme.PRIMARY_HOVER, 
            command=save_action,
            width=100
        )
        save_btn.pack(side="right", padx=6)

        cancel_btn = ctk.CTkButton(
            btn_row, 
            text="取消", 
            fg_color=Theme.SECONDARY_BTN, 
            hover_color=Theme.SECONDARY_BTN_HOVER, 
            command=dialog.destroy,
            width=80
        )
        cancel_btn.pack(side="right")

    def _open_category_manager(self):
        """分类管理面板"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("分类管理")
        dialog.geometry("380x420")
        dialog.configure(fg_color=Theme.BG_ROOT)
        dialog.transient(self)
        dialog.grab_set()

        frm = ctk.CTkFrame(dialog, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(frm, text="📁 分类列表", font=Theme.font_subtitle(), text_color=Theme.TEXT_PRIMARY).pack(anchor="w", pady=(0, 10))

        cat_list_frame = ctk.CTkScrollableFrame(frm, fg_color=Theme.BG_INPUT, height=220)
        cat_list_frame.pack(fill="both", expand=True, pady=(0, 15))

        def refresh_cat_list():
            for w in cat_list_frame.winfo_children():
                w.destroy()
            for cat in self.library_data.get("categories", []):
                row = ctk.CTkFrame(cat_list_frame, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_SM)
                row.pack(fill="x", pady=2, padx=2)
                ctk.CTkLabel(row, text=cat, font=Theme.font_body(), text_color=Theme.TEXT_PRIMARY).pack(side="left", padx=8, pady=4)
                if cat != "我的收藏":
                    del_b = ctk.CTkButton(
                        row, 
                        text="✕", 
                        width=24, 
                        height=24, 
                        fg_color="transparent", 
                        hover_color=Theme.DANGER_BTN_HOVER,
                        text_color=Theme.ERROR,
                        command=lambda c=cat: delete_cat(c)
                    )
                    del_b.pack(side="right", padx=4)

        def delete_cat(cat_name):
            self.library_data["categories"] = [c for c in self.library_data.get("categories", []) if c != cat_name]
            save_prompt_library(self.library_data)
            refresh_cat_list()
            self._update_categories_in_main_view()

        def add_cat():
            new_name = add_entry.get().strip()
            if not new_name:
                return
            if new_name in self.library_data.get("categories", []):
                messagebox.showinfo("提示", "该分类已存在")
                return
            self.library_data.setdefault("categories", []).append(new_name)
            save_prompt_library(self.library_data)
            add_entry.delete(0, "end")
            refresh_cat_list()
            self._update_categories_in_main_view()

        refresh_cat_list()

        add_box = ctk.CTkFrame(frm, fg_color="transparent")
        add_box.pack(fill="x")

        add_entry = ctk.CTkEntry(add_box, placeholder_text="输入新分类名称...", fg_color=Theme.BG_INPUT, height=32)
        add_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        add_btn = ctk.CTkButton(add_box, text="添加", width=65, height=32, fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER, command=add_cat)
        add_btn.pack(side="right")

    def _update_categories_in_main_view(self):
        cats = ["全部分类"] + self.library_data.get("categories", ["我的收藏"])
        self.cat_menu.configure(values=cats)
        if self.cat_var.get() not in cats:
            self.cat_var.set("全部分类")
        self._refresh_prompt_list()
