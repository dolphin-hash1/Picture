import sys
import subprocess

# ================= 依赖自检与按需安装 =================
def install_requirements():
    reqs = ['websocket-client', 'requests', 'customtkinter', 'pillow', 'cryptography']
    print("正在检查并安装缺失的依赖: ", reqs)
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q'] + reqs)

try:
    import customtkinter as ctk
    from PIL import Image
    import websocket
    from cryptography.fernet import Fernet
except ImportError:
    install_requirements()
    import customtkinter as ctk
    from PIL import Image
    import websocket
    from cryptography.fernet import Fernet

# 导入核心模块与 UI
from core.config import (
    SERVER_ADDRESS,
    WORKFLOW_FILE,
    OUTPUT_DIR,
    CLIENT_ID,
    ENCRYPTION_PASSWORD,
    cipher,
    ensure_dirs
)
from core.client import queue_prompt, get_image, get_history
from ui.main_window import ComfyUIApp

if __name__ == "__main__":
    app = ComfyUIApp()
    app.mainloop()