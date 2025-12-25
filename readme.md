# S2S_doubao_esp32s3_Agent

一个用于将 ESP32‑S3 设备与后端实时对话/语音服务桥接的轻量级工程。工程包含两部分：

- Agent_Server：运行在主机/服务器上的桥接服务，负责接收来自 ESP32 的音频流、转发给实时对话客户端并把返回的音频/控制消息下发给 ESP32。
- esp32_client.py：在 ESP32‑S3（MicroPython）上运行的示例客户端，使用 I2S 进行采集与播放，通过 WebSocket 将音频以二进制帧双向传输到服务端，实现低延迟的实时语音通道。

---

## 主要特性

- 基于 I2S 硬件缓冲的“暴力缓冲”策略，减少软件队列与协程切换带来的抖动。
- 双向 WebSocket 音频传输（binary = 音频数据，text = 控制/事件）。
- 服务端负责音频管理、会话桥接和与上游实时对话客户端（例如 LLM 或语音合成/识别服务）的交互。
- 提供示例代码，方便在 ESP32‑S3 上快速验证。

---

## 仓库结构（重要文件说明）

- Agent_Server/
  - main.py — 服务器入口脚本（启动 WebSocket 服务 / 桥接逻辑）
  - esp32_server.py — 处理 ESP32 端连接的服务逻辑
  - realtime_dialog_client.py — 与上游实时对话/语音服务交互的客户端
  - audio_manager.py — 音频文件处理 / 播放队列相关工具
  - bridge_session.py — 会话桥接与状态管理
  - protocol.py — 服务端/客户端之间使用的协议定义（消息类型、控制命令等）
  - config.py — 服务端配置（端口、上游服务地址、API KEY 等）
  - requirements.txt — Python 服务端依赖
  - 若干示例音频（*.wav）用于测试
- esp32_client.py — ESP32‑S3 端示例（MicroPython 风格）

---

## 快速开始

下面给出服务端与设备端的快速启动指导。

### 1) 服务端 (Agent_Server)

先确保系统上有 Python 3.8+（推荐 3.10+）并创建虚拟环境：

```bash
cd Agent_Server
python3 -m venv .venv
source .venv/bin/activate   # Linux / macOS
# 或 Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

配置：
- 编辑 `Agent_Server/config.py`，根据你的环境修改监听主机/端口、上游实时对话服务地址或 API Key 等。

运行：
```bash
# 在虚拟环境已激活的情况下
python main.py
```

启动后，服务会监听来自 ESP32 的 WebSocket 连接并在接入上游实时客户端后进行桥接。

日志和调试：
- 查看控制台输出以确认 WebSocket 建连、会话创建、音频收发等流程。
- `audio_manager.py` 中有音频播放/文件保存的辅助函数，便于排查音频编码/格式问题。

### 2) ESP32‑S3 端（esp32_client.py）

说明：
- 该脚本为 MicroPython/类 MicroPython 环境下的示例客户端，使用硬件 I2S 做采集与播放，并用 WebSocket 双向传输音频二进制帧。
- 请根据实际硬件调整引脚与采样率设置。

主要要修改的项（在文件顶部）：
- WIFI_SSID / WIFI_PASSWORD：你的 WiFi 名称和密码
- SERVER_URL：指向运行了 Agent_Server 的地址，如 `ws://192.168.1.6:8765`

上传与运行方式（常用工具）：
- 使用 mpremote / ampy / rshell / Thonny 等工具把 `esp32_client.py` 上传到设备，或将其重命名为 `main.py` 放到设备根目录以自动启动。
- 确保设备刷入了支持 I2S 的 MicroPython 固件，并具备 WebSocket 客户端库（或对脚本中相关导入进行替换以匹配你设备上可用的库）。

示例（使用 mpremote）：
```bash
mpremote connect <your-device> fs cp esp32_client.py :/main.py
mpremote connect <your-device> run /main.py
```

注意：示例代码中使用了 I2S 的配置：
- 录音：采样率 16000 Hz、16-bit、单声道
- 播放：采样率 24000 Hz（根据需要可调整）
- 播放端使用较大 ibuf 以利用硬件 DMA 缓冲、减少丢帧

---

## 协议说明（简要）

- 二进制消息（WebSocket binary frames）：音频 PCM 数据块，直接写入 I2S 播放缓冲。
- 文本消息（WebSocket text frames）：控制/事件消息（例如通知停止播放、切换模式等）。
- 服务端在接收到控制消息（如 `"stop"`）时会采取相应措施（示例代码通过重建 I2S 来清空缓冲）。

（详细协议定义可参考 Agent_Server/protocol.py）

---

## 开发与调试建议

- 本工程采用“硬件缓冲优先”思路：尽量依赖 I2S 的 DMA 缓存来做背压，减少 Python 层的队列与内存拷贝，适合对延迟较敏感的场景。
- 如果遇到音频抖动或丢帧问题：
  - 优先检查硬件 I2S ibuf 设置与采样率是否匹配。
  - 检查网络抖动：在服务端与 ESP32 之间尽量使用局域网。
  - 在 ESP32 端减少其它耗时操作，尽量把接收与播放合并到同一个循环中（示例中已体现）。
- 如果你在 MicroPython 上无法使用示例中某些库（例如 aiohttp），可以：
  - 替换为适配 MicroPython 的 WebSocket 客户端实现（如 uwebsockets），或
  - 在 ESP32 上运行更完整的 Python 解释器（如果可行），或
  - 适配 ESP 端代码为标准的 MicroPython 风格（将 aiohttp 改为可用模块）。

---

## 常见问题

- 无法连接 WiFi：确认 `WIFI_SSID` / `WIFI_PASSWORD` 正确并且设备在路由器覆盖范围内。
- 设备连接上但无音频：确认 I2S 引脚配置正确、麦克风/喇叭已连接，并检查采样率/位深一致性。
- 服务端无法接收数据：查看 `main.py` 的日志，确认 WebSocket 端点正确（与 esp32 的 SERVER_URL 一致）、防火墙允许端口访问。

---

## 致谢

感谢所有参考与启发的开源项目，以及对低延迟语音交互优化思路的讨论。

---

## 许可与贡献

- 当前仓库未在顶层声明许可（LICENSE）。如果你打算公开或分发，请在仓库中添加合适的 LICENSE 文件（例如 MIT）。
- 欢迎提交 Issue 或 PR，描述你遇到的问题或希望添加的功能。

---

如果你愿意，我可以：
- 帮你把这个 README 写入仓库的 `readme.md`（需要你的确认以执行写入操作），
- 或者把 README 的英文版本一起生成，或根据你实际的 config.py、main.py 内容把文档再细化成配置示例与运行截图说明。