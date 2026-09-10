import json
import urllib.request
import urllib.parse
import websocket
import random
import time
import io
from PIL import Image
from core.config import SERVER_ADDRESS, CLIENT_ID, WORKFLOW_FILE, OUTPUT_DIR, cipher

def queue_prompt(prompt_workflow):
    """向 ComfyUI 提交工作流任务"""
    payload = {"prompt": prompt_workflow, "client_id": CLIENT_ID}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(f"http://{SERVER_ADDRESS}/prompt", data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def get_image(filename, subfolder, folder_type):
    """从 ComfyUI 获取生成的图像字节流"""
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/view?{url_values}") as response:
        return response.read()

def get_history(prompt_id):
    """获取指定任务的历史输出数据"""
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/history/{prompt_id}") as response:
        return json.loads(response.read())

def decrypt_image_data(data_bytes):
    """尝试解密图像数据，若非加密格式则直接返回原数据"""
    try:
        return cipher.decrypt(data_bytes)
    except Exception:
        return data_bytes

def encrypt_and_save_image(image_bytes, node_id, index):
    """使用 Fernet 加密图像数据并持久化保存到本地"""
    timestamp = int(time.time())
    file_name = f"{OUTPUT_DIR}/output_{timestamp}_{node_id}_{index}.enc"
    encrypted_data = cipher.encrypt(image_bytes)
    with open(file_name, "wb") as f:
        f.write(encrypted_data)
    return file_name

def execute_generation_task(user_prompt, msg_queue):
    """
    后台执行单个生成任务。
    严格维持现有节点 17 (LM Studio) 和采样器种子随机机制，
    同时统计耗时并回传图片元数据。
    """
    start_time = time.time()
    try:
        # 1. 读取工作流配置
        with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
            prompt_workflow = json.load(f)
        
        # 2. 动态注入 prompt 与打破缓存
        if "17" in prompt_workflow:
            prompt_workflow["17"]["inputs"]["user_message"] = user_prompt
            if "temperature" in prompt_workflow["17"]["inputs"]:
                base_temp = prompt_workflow["17"]["inputs"]["temperature"]
                prompt_workflow["17"]["inputs"]["temperature"] = round(base_temp + random.uniform(-0.0050, 0.0050), 4)
            else:
                prompt_workflow["17"]["inputs"]["user_message"] += f"\n<!-- Bypass Cache: {random.randint(1, 1000000)} -->"

        # 随机化采样种子
        if "5" in prompt_workflow and "inputs" in prompt_workflow["5"]:
            prompt_workflow["5"]["inputs"]["seed"] = random.randint(1, 10**15)
        if "12" in prompt_workflow and "inputs" in prompt_workflow["12"]:
            prompt_workflow["12"]["inputs"]["seed"] = random.randint(1, 10**15)

        msg_queue.put(("status", "正在连接 ComfyUI 引擎..."))
        
        ws = websocket.WebSocket()
        ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={CLIENT_ID}")

        msg_queue.put(("status", "提交任务队列中..."))
        prompt_res = queue_prompt(prompt_workflow)
        prompt_id = prompt_res['prompt_id']

        msg_queue.put(("status", "LM Studio 思考中 & ComfyUI 准备中..."))

        # 解析节点标题
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
                mtype = message.get('type')
                
                if mtype == 'executing':
                    data = message['data']
                    node_id = data.get('node')
                    if node_id is None and data.get('prompt_id') == prompt_id:
                        msg_queue.put(("status", "生成完毕！正在获取图像数据..."))
                        break
                    elif node_id is not None:
                        current_stage = node_titles.get(str(node_id), f"节点 {node_id}")
                        msg_queue.put(("status", f"当前阶段: {current_stage} ..."))

                elif mtype == 'progress':
                    data = message['data']
                    max_val = data.get('max', 1)
                    val = data.get('value', 0)
                    progress = val / max_val if max_val > 0 else 0
                    msg_queue.put(("progress", progress))
                    msg_queue.put(("status", f"阶段: {current_stage} - 进度: {val}/{max_val}"))

        ws.close()

        # 3. 获取并保存生成的图像
        elapsed_sec = round(time.time() - start_time, 2)
        history = get_history(prompt_id).get(prompt_id, {})
        outputs = history.get('outputs', {})

        for node_id, node_output in outputs.items():
            if 'images' in node_output:
                for i, img_item in enumerate(node_output['images']):
                    img_bytes = get_image(img_item['filename'], img_item['subfolder'], img_item['type'])
                    saved_path = encrypt_and_save_image(img_bytes, node_id, i)
                    
                    # 读取图片元信息
                    try:
                        pil_img = Image.open(io.BytesIO(img_bytes))
                        width, height = pil_img.size
                        fmt = pil_img.format or "PNG"
                    except Exception:
                        width, height, fmt = 0, 0, "PNG"

                    meta = {
                        "elapsed": elapsed_sec,
                        "width": width,
                        "height": height,
                        "format": fmt,
                        "saved_path": saved_path,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    msg_queue.put(("image", (img_bytes, meta)))

        msg_queue.put(("status", f"🎉 完成！总耗时: {elapsed_sec}s"))
        msg_queue.put(("done", ""))

    except ConnectionRefusedError:
        msg_queue.put(("error", "无法连接到 ComfyUI，请检查是否已启动 (127.0.0.1:8188)"))
        raise
    except Exception as e:
        msg_queue.put(("error", f"生成异常: {e}"))
        raise
