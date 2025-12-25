# S2S_doubao_esp32s3_Agent

一个用于将 ESP32‑S3 设备与上游实时对话/语音服务进行低延迟桥接的轻量级工程。项目分为两部分：

- Agent_Server：运行在主机/服务器上的桥接服务，负责接收来自 ESP32 的音频流、与上游实时会话客户端交互，并把返回的音频与控制消息下发给设备。
- esp32_client.py：在 ESP32‑S3（MicroPython 风格）上运行的示例客户端，使用 I2S 进行采集与播放，通过 WebSocket 双向传输音频（binary = 音频数据，text = 控制/事件）。

---

## 主要特性

- 以硬件 I2S DMA 缓冲为主的“硬件缓冲优先”策略，降低软件层队列与协程切换带来的抖动。
- 双向 WebSocket 传输：二进制帧用于音频流，文本帧用于控制与事件。
- 服务端负责会话管理、音频文件处理与上游实时对话客户端的适配（ASR/TTS/LLM）。
- 提供 ESP32 端示例，便于在实际硬件上快速验证与调试。

---

## 仓库结构（重要文件说明）

- Agent_Server/
  - `main.py` — 服务端入口（启动 WebSocket 服务与桥接逻辑）
  - `esp32_server.py` — 处理 ESP32 端连接与设备级逻辑
  - `realtime_dialog_client.py` — 与上游实时对话/语音服务交互的适配器
  - `audio_manager.py` — 音频读写、格式转换、保存等辅助函数
  - `bridge_session.py` — 会话管理与消息路由（设备 ↔ 上游）
  - `protocol.py` — 协议定义（消息类型与控制命令）
  - `config.py` — 服务端配置（监听地址、上游地址、API KEY 等）
  - `requirements.txt` — Python 依赖列表
  - 若干示例音频（用于本地测试）
- `esp32_client.py` — ESP32‑S3（MicroPython）示例客户端
- `readme.md` — 本文件

---

## 设计与协议要点

- 二进制 WebSocket 帧：直接承载 PCM 音频数据块，服务端收到后可直接转发或写入文件用于调试。
- 文本 WebSocket 帧：控制/事件消息（例如 `{"type":"control","action":"stop"}` 或会话元信息）。
- 服务端职责：接收设备音频 → 转发/送入上游实时客户端 → 将上游返回的音频二进制帧下发给设备；并在必要时通过文本帧下发控制命令。
- 设计原则：在设备端尽量依赖 I2S 硬件缓冲以降低延迟与丢帧风险，服务端负责集中管理与与上游协议的对接。

---

## 环境与依赖

服务端（Agent_Server）：
- Python 3.8+（推荐 3.10+）
- 依赖见 `Agent_Server/requirements.txt`（例如 aiohttp、websockets、pydub/soundfile 等根据适配器而异）

ESP32 设备端：
- ESP32‑S3 开发板，刷入支持 I2S 的 MicroPython 固件（或能使用示例中 WebSocket 客户端的环境）
- I2S 麦克风与 I2S DAC/扬声器或支持 I2S 的音频外设

---

## 快速开始 — 服务端（Agent_Server）

1. 创建虚拟环境并安装依赖：
```bash
cd Agent_Server
python3 -m venv .venv
source .venv/bin/activate   # Linux / macOS
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. 配置：
- 编辑 `Agent_Server/config.py`，常见需设置项：
  - SERVER_HOST（例如 "0.0.0.0"）
  - SERVER_PORT（例如 8765）
  - UPSTREAM_URL（上游实时服务的地址，如 wss://...）
  - API_KEY（若上游需要）
  - AUDIO_SAVE_PATH、LOG_LEVEL 等

示例（伪代码）：
```py
# config.py
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8765
UPSTREAM_URL = "wss://upstream.example.com/realtime"
API_KEY = "sk-..."
AUDIO_SAVE = True
```

3. 启动服务：
```bash
python main.py
```
- 服务启动后会监听 WebSocket 连接，日志会输出设备连接、会话创建、音频收发等信息。

---

## 快速开始 — ESP32‑S3（esp32_client.py）

说明：
- 示例基于 MicroPython 风格实现，使用 I2S 进行录音/播放并通过 WebSocket 传输二进制音频帧与文本控制帧。
- 请根据你的硬件调整脚位、采样率与缓冲区大小；如设备上无 aiohttp，可替换成 uwebsockets 等可用库。

需要修改的项（文件顶部）：
- WIFI_SSID / WIFI_PASSWORD：WiFi 名称与密码
- SERVER_URL：指向运行 Agent_Server 的地址，例如 `ws://192.168.1.6:8765`
- I2S 引脚、采样率（采样与播放率可能不同，按需要调整）

上传与运行（示例使用 mpremote）：
```bash
mpremote connect <your-device> fs cp esp32_client.py :/main.py
mpremote connect <your-device> run /main.py
```

注意：
- 示例默认录音 16 kHz、16-bit 单声道；播放可使用 24 kHz 或其它，根据硬件选型调整。
- 在播放端使用较大的 ibuf 值以利用硬件 DMA 缓冲，减少丢帧。

---

## 常见问题排查

- 无法连接 WiFi：
  - 检查 WIFI_SSID/WIFI_PASSWORD 是否正确，确认设备在路由器覆盖范围内。
- 设备连接上但无音频：
  - 检查 I2S 引脚接线、麦克风/扬声器是否供电并正确初始化、采样率与位深是否一致。
- 服务端未收到数据：
  - 检查 `main.py` 日志确认 WebSocket 握手是否成功；确认 `SERVER_URL` 与 `config.py` 中的端口一致；防火墙是否阻挡端口。
- 音频抖动或丢帧：
  - 增大 I2S ibuf，减少设备端其它阻塞任务，确保使用局域网以降低网络抖动。
- 文本消息解析错误：
  - 确认文本帧遵循 `protocol.py` 中定义的格式（JSON 字段与类型）。

---

## 开发与扩展建议

- 将上游适配逻辑写在 `realtime_dialog_client.py`：根据上游 API（ASR/TTS/LLM），实现音频转发、事件回调与鉴权流程。
- `bridge_session.py` 管理会话生命周期与状态转换，阅读该文件能快速了解设备与上游之间的路由逻辑。
- `audio_manager.py` 提供音频保存、重采样与格式转换的工具，便于在调试时保存原始音频以分析问题。

---

## 协议示例（简要）

- 文本控制示例：
```json
{"type":"control","action":"stop"}
{"type":"meta","session_id":"abc123","sample_rate":16000}
```
- 二进制帧：固定大小的 PCM 数据块（服务端/设备应约定 chunk 大小或以 I2S 缓冲对齐）。

完整消息类型与字段请参考 `Agent_Server/protocol.py`。

---

## 许可与贡献

- 当前仓库顶层未包含 LICENSE 文件。若计划公开或分发，请在仓库中添加合适的许可证（例如 MIT）。
- 欢迎提交 Issue 或 PR —— 请在描述中包含复现步骤与日志输出，便于定位问题。

---

如果你希望，我可以：
- 帮你把本中文 README 写入仓库（需要你确认允许我进行写入以及目标分支），
- 或者根据 `Agent_Server/config.py` 与 `main.py` 的实际内容把 README 中的配置示例改写为精确的配置片段并同步更新。