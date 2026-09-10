# ComfyUI 创作工作台

面向单个 ComfyUI API 工作流的 Windows 桌面前端。它连接本机 ComfyUI 和现有 LM Studio 节点，提供参数化生成、可取消任务队列、加密图库及可复现的作品参数。

## 运行

1. 使用 Python 3.10+ 安装依赖：`python -m pip install -r requirements.txt`
2. 启动本机 ComfyUI（默认地址 `127.0.0.1:8188`）。
3. 运行：`python comfy_ui.py`

首次启动会在 `%APPDATA%\ComfyUIWorkbench` 创建设置和由 Windows DPAPI 保护的图库密钥。图库里的图片和生成元数据均以 Fernet 加密保存；请勿删除该目录中的密钥文件，否则原有图库无法解锁。

可在应用的“设置”中修改 ComfyUI 地址、API 工作流 JSON 和图库目录。修改后重启应用即可重新验证配置。
