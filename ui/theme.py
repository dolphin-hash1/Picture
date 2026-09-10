import customtkinter as ctk

class Theme:
    """现代深空极简风 (Sleek Dark Studio) 视觉体系"""
    # 基础背景分层
    BG_ROOT = "#0D0E12"          # 主窗口最底层深空黑
    BG_SIDEBAR = "#14161D"       # 左侧面板
    BG_CARD = "#1A1D26"          # 卡片容器背景
    BG_CARD_ALT = "#161820"      # 次级卡片背景
    BG_CARD_HOVER = "#232734"    # 悬浮态卡片
    BG_INPUT = "#111218"         # 输入框及下拉框底层

    # 边框与微分割线
    BORDER_SUBTLE = "#232633"    # 弱分割线
    BORDER_DEFAULT = "#2D3142"   # 标准卡片边框
    BORDER_HOVER = "#434963"     # 悬停卡片边框
    BORDER_FOCUS = "#6366F1"     # 聚焦高亮边框

    # 品牌与功能强调色
    PRIMARY = "#6366F1"          # 现代靛紫 (Indigo)
    PRIMARY_HOVER = "#4F46E5"    # 悬浮深化
    PRIMARY_ACTIVE = "#4338CA"   # 按下
    ACCENT_CYAN = "#06B6D4"      # 科技青点缀 (Cyan)
    ACCENT_PURPLE = "#A855F7"    # 渐变紫色

    # 状态指示色
    SUCCESS = "#10B981"          # 成功绿
    WARNING = "#F59E0B"          # 警示黄
    ERROR = "#EF4444"            # 错误红
    INFO = "#38BDF8"             # 提示蓝

    # 按钮次级状态
    SECONDARY_BTN = "#222532"
    SECONDARY_BTN_HOVER = "#2C3040"
    DANGER_BTN = "#3F1D24"
    DANGER_BTN_HOVER = "#59232D"

    # 文字排版色阶
    TEXT_PRIMARY = "#F9FAFB"     # 一级标题及高亮正文
    TEXT_SECONDARY = "#A0AEC0"   # 二级说明与标签
    TEXT_MUTED = "#64748B"       # 弱化辅助信息与占位符
    TEXT_ACCENT = "#818CF8"      # 强调文本色

    # 标准圆角
    RADIUS_SM = 6
    RADIUS_MD = 10
    RADIUS_LG = 14
    RADIUS_FULL = 999

    @classmethod
    def apply_global_settings(cls):
        """应用 CustomTkinter 全局深色外观规范"""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

    @classmethod
    def font_title(cls):
        return ctk.CTkFont(family="Microsoft YaHei UI", size=20, weight="bold")

    @classmethod
    def font_subtitle(cls):
        return ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold")

    @classmethod
    def font_body(cls):
        return ctk.CTkFont(family="Microsoft YaHei UI", size=13)

    @classmethod
    def font_body_bold(cls):
        return ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold")

    @classmethod
    def font_caption(cls):
        return ctk.CTkFont(family="Microsoft YaHei UI", size=11)

    @classmethod
    def font_icon(cls):
        return ctk.CTkFont(family="Segoe UI Emoji", size=14)
