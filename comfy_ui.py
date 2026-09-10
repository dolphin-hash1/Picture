import sys
import subprocess
import threading
import queue
import random

# 自动安装所需的依赖
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

import uuid
import json
import urllib.request
import urllib.parse
import time
import os
import io
import base64
import hashlib

# ================= 加密配置 =================
ENCRYPTION_PASSWORD = b"ComfyUI_Secret_Password"
_key = base64.urlsafe_b64encode(hashlib.sha256(ENCRYPTION_PASSWORD).digest())
cipher = Fernet(_key)

# ================= 配置区 =================
SERVER_ADDRESS = "127.0.0.1:8188" 
WORKFLOW_FILE = r"D:\Code\Python\ComfyUI\workflow_api.json"  
OUTPUT_DIR = r"D:\Code\Python\ComfyUI\outputs"
CLIENT_ID = str(uuid.uuid4())
# ==========================================

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": CLIENT_ID}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request("http://{}/prompt".format(SERVER_ADDRESS), data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(SERVER_ADDRESS, url_values)) as response:
        return response.read()

def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(SERVER_ADDRESS, prompt_id)) as response:
        return json.loads(response.read())

class ComfyUIApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("ComfyUI Image Generator")
        self.geometry("1100x750")
        
        # 设置主题颜色：现代化深色风格
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # --- 左侧控制面板 ---
        self.sidebar_frame = ctk.CTkFrame(self, width=320, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="🎨 ComfyUI 控制台", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))
        
        self.prompt_label = ctk.CTkLabel(self.sidebar_frame, text="输入画面描述:", font=ctk.CTkFont(size=14))
        self.prompt_label.grid(row=1, column=0, padx=20, pady=(10, 5), sticky="w")
        
        self.prompt_textbox = ctk.CTkTextbox(self.sidebar_frame, height=180, font=ctk.CTkFont(size=14))
        self.prompt_textbox.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.prompt_textbox.insert("0.0", "")
        
        # 生成选项
        self.options_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.options_frame.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        self.count_label = ctk.CTkLabel(self.options_frame, text="生成数量:", font=ctk.CTkFont(size=14))
        self.count_label.pack(side="left", padx=(0, 10))
        
        self.count_var = ctk.StringVar(value="1张")
        self.count_menu = ctk.CTkOptionMenu(
            self.options_frame, 
            values=["1张", "2张", "3张", "4张", "5张", "10张"],
            variable=self.count_var,
            width=100
        )
        self.count_menu.pack(side="left")
        
        self.generate_button = ctk.CTkButton(
            self.sidebar_frame, 
            text="🚀 开始生成", 
            command=self.start_generation, 
            height=45, 
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.generate_button.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        
        # 底部进度条与状态栏
        self.progress_bar = ctk.CTkProgressBar(self.sidebar_frame, height=12)
        self.progress_bar.grid(row=6, column=0, padx=20, pady=(10, 0), sticky="ew")
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="状态: 待机中", 
            font=ctk.CTkFont(size=13), 
            text_color="gray", 
            justify="left", 
            wraplength=280,
            height=60,
            anchor="sw"
        )
        self.status_label.grid(row=7, column=0, padx=20, pady=20, sticky="sw")
        
        # --- 右侧图像展示区 ---
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        self.tab_current = self.tabview.add("当前图片")
        self.tab_gallery = self.tabview.add("历史画廊")
        
        # - 当前图片 Tab
        self.tab_current.grid_rowconfigure(0, weight=1)
        self.tab_current.grid_columnconfigure(0, weight=1)
        
        self.image_label = ctk.CTkLabel(self.tab_current, text="暂无图片", font=ctk.CTkFont(size=20), text_color="gray")
        self.image_label.grid(row=0, column=0, sticky="nsew")
        
        # - 历史画廊 Tab
        self.tab_gallery.grid_rowconfigure(1, weight=1)
        self.tab_gallery.grid_columnconfigure(0, weight=1)
        
        self.refresh_btn = ctk.CTkButton(self.tab_gallery, text="🔄 刷新画廊", command=self.load_gallery_thread)
        self.refresh_btn.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        
        self.gallery_scroll = ctk.CTkScrollableFrame(self.tab_gallery)
        self.gallery_scroll.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        self.after(500, self.load_gallery_thread)
        
        # --- 后台通信 ---
        self.queue = queue.Queue()
        self.task_queue = queue.Queue()
        self.is_generating = False
        
        # 定时器，用于从队列中读取更新 UI
        self.after(100, self.process_queue)

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.queue.get_nowait()
                if msg_type == "status":
                    self.status_label.configure(text=f"状态: {data}", text_color="white")
                elif msg_type == "progress":
                    self.progress_bar.set(data)
                elif msg_type == "image":
                    self.tabview.set("当前图片")
                    self.display_image(data)
                elif msg_type == "done":
                    self.progress_bar.set(1.0)
                elif msg_type == "all_done":
                    self.is_generating = False
                    self.generate_button.configure(text="🚀 开始生成")
                    self.progress_bar.set(1.0)
                elif msg_type == "update_queue_status":
                    q_size = self.task_queue.qsize()
                    if q_size > 0:
                        self.generate_button.configure(text=f"🚀 添加排队 (排队中: {q_size})")
                    else:
                        self.generate_button.configure(text="⏳ 生成中...")
                elif msg_type == "error":
                    self.status_label.configure(text=f"错误: {data}", text_color="#ff5555")
                    self.progress_bar.set(1.0)
                elif msg_type == "gallery_clear":
                    for widget in self.gallery_scroll.winfo_children():
                        widget.destroy()
                    self.gallery_row, self.gallery_col = 0, 0
                elif msg_type == "gallery_item":
                    img_path, img_name, img_size, img_data = data
                    try:
                        img = Image.open(io.BytesIO(img_data))
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img_size)
                        
                        btn = ctk.CTkButton(
                            self.gallery_scroll, 
                            image=ctk_img, 
                            text="", 
                            fg_color="transparent",
                            hover_color="#333333",
                            command=lambda p=img_path: self.view_historical_image(p)
                        )
                        btn.grid(row=self.gallery_row, column=self.gallery_col, padx=10, pady=10)
                        
                        lbl = ctk.CTkLabel(self.gallery_scroll, text=img_name[:15]+"...", font=ctk.CTkFont(size=10))
                        lbl.grid(row=self.gallery_row+1, column=self.gallery_col, padx=10, pady=(0, 10))
                        
                        self.gallery_col += 1
                        if self.gallery_col >= 3:
                            self.gallery_col = 0
                            self.gallery_row += 2
                    except Exception as e:
                        print(f"Error loading thumbnail {img_name}: {e}")
                elif msg_type == "gallery_done":
                    self.refresh_btn.configure(state="normal", text="🔄 刷新画廊")
        except queue.Empty:
            pass
        # 持续循环监听
        self.after(100, self.process_queue)

    def display_image(self, image_data):
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # 动态获取主窗口物理尺寸
            phys_w = self.winfo_width()
            phys_h = self.winfo_height()
            
            # 获取 CustomTkinter 的系统级 DPI 缩放比例 (window_scaling)
            # 高分屏 (如 4K) 下系统会自动放大 UI，此时 window_scaling 可能是 1.5 或 2.0
            try:
                scaling = self._get_window_scaling()
            except AttributeError:
                scaling = 1.0
                
            # 将物理像素转换为逻辑像素，统一单位进行计算
            logical_w = phys_w / scaling
            logical_h = phys_h / scaling
            
            if logical_w < 100 or logical_h < 100:
                logical_w, logical_h = 1000, 650
                
            # 计算可用区域的逻辑宽度：总宽 - 左侧栏(320) - 外边距(40) - 内边距(20)
            frame_w = logical_w - 380
            # 计算可用区域的逻辑高度：总高 - 外边距(40) - 顶部Tab栏(~40) - 内边距(20)
            frame_h = logical_h - 100
                
            w, h = image.size
            ratio = min(frame_w/w, frame_h/h)
            new_size = (int(w*ratio), int(h*ratio))
            
            # CTkImage 接收逻辑像素，并自动根据 DPI 高清渲染
            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=new_size)
            self.image_label.configure(image=ctk_image, text="")
            self.image_label._image_ref = ctk_image  # 强制保留引用，防止垃圾回收导致黑块
        except Exception as e:
            self.queue.put(("error", f"图片加载失败: {e}"))

    def view_historical_image(self, path):
        try:
            with open(path, "rb") as f:
                encrypted_data = f.read()
            
            # 尝试解密，如果失败可能是旧的未加密文件
            try:
                image_data = cipher.decrypt(encrypted_data)
            except Exception:
                image_data = encrypted_data
                
            self.tabview.set("当前图片")
            self.display_image(image_data)
        except Exception as e:
            self.queue.put(("error", f"无法打开图片: {e}"))

    def load_gallery_thread(self):
        self.refresh_btn.configure(state="disabled", text="⏳ 加载中...")
        threading.Thread(target=self._load_gallery_worker, daemon=True).start()
        
    def _load_gallery_worker(self):
        self.queue.put(("gallery_clear", None))
        
        if not os.path.exists(OUTPUT_DIR):
            self.queue.put(("gallery_done", None))
            return
            
        images = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(('.png', '.jpg', '.jpeg', '.enc'))]
        images.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)), reverse=True)
        images = images[:30] # Limit to 30 to keep it fast
        
        for img_name in images:
            img_path = os.path.join(OUTPUT_DIR, img_name)
            try:
                with open(img_path, "rb") as f:
                    encrypted_data = f.read()
                
                try:
                    image_data = cipher.decrypt(encrypted_data)
                except Exception:
                    image_data = encrypted_data
                    
                img = Image.open(io.BytesIO(image_data))
                img.thumbnail((250, 250))
                
                # Save thumbnail bytes to pass to main thread
                thumb_io = io.BytesIO()
                img.save(thumb_io, format="PNG")
                
                self.queue.put(("gallery_item", (img_path, img_name, img.size, thumb_io.getvalue())))
            except Exception as e:
                print(f"Error loading thumbnail {img_name}: {e}")
                
        self.queue.put(("gallery_done", None))

    def start_generation(self):
        user_prompt = self.prompt_textbox.get("0.0", "end").strip()
        if not user_prompt:
            self.status_label.configure(text="状态: 请输入画面描述", text_color="#ff5555")
            return
            
        count_str = self.count_var.get().replace("张", "")
        try:
            count = int(count_str)
        except ValueError:
            count = 1
            
        for _ in range(count):
            self.task_queue.put(user_prompt)
            
        if self.is_generating:
            # 已经在生成中了，只需要更新排队信息
            self.queue.put(("update_queue_status", ""))
        else:
            self.is_generating = True
            self.queue.put(("update_queue_status", ""))
            self.queue.put(("status", "准备生成..."))
            # 启动后台任务调度线程
            threading.Thread(target=self.job_worker_thread, daemon=True).start()

    def job_worker_thread(self):
        while not self.task_queue.empty():
            current_prompt = self.task_queue.get()
            self.queue.put(("update_queue_status", ""))
            self.queue.put(("progress", 0))
            
            self.generate_task(current_prompt)
            
            self.task_queue.task_done()
            self.queue.put(("done", ""))
            
        self.queue.put(("all_done", ""))

    def generate_task(self, user_prompt):
        try:
            # 1. 读取工作流文件
            with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
                prompt_workflow = json.load(f)
            
            # 2. 动态修改参数
            # 修改 LM Studio 节点的 prompt (节点 ID 17)
            if "17" in prompt_workflow:
                prompt_workflow["17"]["inputs"]["user_message"] = user_prompt
                
                # 随机微调 temperature 或注入随机数来打破 ComfyUI 的缓存机制，强制每次都请求 LM Studio
                if "temperature" in prompt_workflow["17"]["inputs"]:
                    base_temp = prompt_workflow["17"]["inputs"]["temperature"]
                    # 加上极小随机数产生不同 hash 且基本不影响生成效果
                    prompt_workflow["17"]["inputs"]["temperature"] = round(base_temp + random.uniform(-0.0050, 0.0050), 4)
                else:
                    # 作为后备方案，如果不存在 temperature 参数，在 prompt 尾部加入随机字符串
                    prompt_workflow["17"]["inputs"]["user_message"] += f"\n<!-- Bypass Cache: {random.randint(1, 1000000)} -->"
                
            # 随机化种子，使得每次生成的图像都不一样
            if "5" in prompt_workflow:
                prompt_workflow["5"]["inputs"]["seed"] = random.randint(1, 10**15)
            if "12" in prompt_workflow:
                prompt_workflow["12"]["inputs"]["seed"] = random.randint(1, 10**15)
                
            self.queue.put(("status", "正在连接到 ComfyUI..."))
            
            ws = websocket.WebSocket()
            ws.connect("ws://{}/ws?clientId={}".format(SERVER_ADDRESS, CLIENT_ID))
            
            self.queue.put(("status", "提交任务到 ComfyUI..."))
            prompt_id = queue_prompt(prompt_workflow)['prompt_id']
            
            self.queue.put(("status", "LM Studio 思考中 & ComfyUI 绘图中...\n(请注意 ComfyUI 控制台的进度)"))
            
            node_titles = {}
            for node_id, node_info in prompt_workflow.items():
                if isinstance(node_info, dict):
                    if "_meta" in node_info and "title" in node_info["_meta"]:
                        node_titles[str(node_id)] = node_info["_meta"]["title"]
                    else:
                        node_titles[str(node_id)] = node_info.get("class_type", f"节点 {node_id}")

            current_stage = "初始化"
            while True:
                out = ws.recv()
                if isinstance(out, str):
                    message = json.loads(out)
                    if message['type'] == 'executing':
                        data = message['data']
                        node_id = data.get('node')
                        if node_id is None and data.get('prompt_id') == prompt_id:
                            self.queue.put(("status", "生成完毕！正在获取高清图片..."))
                            break
                        elif node_id is not None:
                            current_stage = node_titles.get(str(node_id), f"节点 {node_id}")
                            self.queue.put(("status", f"当前阶段: {current_stage} ..."))

                    elif message['type'] == 'progress':
                        data = message['data']
                        progress = data['value'] / data['max']
                        self.queue.put(("progress", progress))
                        self.queue.put(("status", f"当前阶段: {current_stage} - 渲染进度: {data['value']}/{data['max']}"))
                            
            ws.close()
            
            # 3. 下载并保存图片
            history = get_history(prompt_id)[prompt_id]
            for node_id in history['outputs']:
                node_output = history['outputs'][node_id]
                if 'images' in node_output:
                    for i, image in enumerate(node_output['images']):
                        image_data = get_image(image['filename'], image['subfolder'], image['type'])
                        
                        # 加密并保存到本地输出目录
                        timestamp = int(time.time())
                        file_name = f"{OUTPUT_DIR}/output_{timestamp}_{node_id}_{i}.enc"
                        encrypted_data = cipher.encrypt(image_data)
                        with open(file_name, "wb") as img_file:
                            img_file.write(encrypted_data)
                            
                        # 把图片传给主线程显示
                        self.queue.put(("image", image_data))
                        
            self.queue.put(("status", "🎉 完成！图片已保存。"))
            self.queue.put(("done", ""))
            
        except ConnectionRefusedError:
            self.queue.put(("error", "无法连接到 ComfyUI，请检查是否已启动 (127.0.0.1:8188)。"))
            # 发生连接错误时清空队列
            with self.task_queue.mutex:
                self.task_queue.queue.clear()
        except Exception as e:
            self.queue.put(("error", f"发生异常: {e}"))

if __name__ == "__main__":
    app = ComfyUIApp()
    app.mainloop()