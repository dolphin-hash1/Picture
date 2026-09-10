import os
import uuid
import base64
import hashlib
from cryptography.fernet import Fernet

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ================= 加密配置 =================
ENCRYPTION_PASSWORD = b"ComfyUI_Secret_Password"
_key = base64.urlsafe_b64encode(hashlib.sha256(ENCRYPTION_PASSWORD).digest())
cipher = Fernet(_key)

# ================= 核心路径配置 =================
SERVER_ADDRESS = "127.0.0.1:8188"
CLIENT_ID = str(uuid.uuid4())

# 工作流文件路径配置（优先使用全局指定路径，若不存在则回退至项目根目录同名文件）
PRIMARY_WORKFLOW_FILE = r"D:\Code\Python\ComfyUI\workflow_api.json"
if os.path.exists(PRIMARY_WORKFLOW_FILE):
    WORKFLOW_FILE = PRIMARY_WORKFLOW_FILE
else:
    WORKFLOW_FILE = os.path.join(BASE_DIR, "workflow_api.json")

# 图像输出目录配置（优先尝试 D 盘目录，无法访问或创建时使用项目内 outputs 目录）
PRIMARY_OUTPUT_DIR = r"D:\Code\Python\ComfyUI\outputs"
try:
    if not os.path.exists(PRIMARY_OUTPUT_DIR):
        os.makedirs(PRIMARY_OUTPUT_DIR, exist_ok=True)
    OUTPUT_DIR = PRIMARY_OUTPUT_DIR
except Exception:
    OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

# 提示词库持久化路径
PROMPTS_FILE = os.path.join(BASE_DIR, "prompts_library.json")

def ensure_dirs():
    """确保必要的目录和文件结构完备"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
