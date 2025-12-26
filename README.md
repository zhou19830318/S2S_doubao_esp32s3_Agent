# ESP32 实时语音助手（基于火山引擎）

一个完整的ESP32实时语音对话系统，通过火山引擎的语音技术实现智能语音交互。

## 🌟 项目概述

本项目将带你从零开始构建一个功能强大的ESP32实时语音对话系统。利用火山引擎的语音技术，配合Python中转服务器，让ESP32开发板也能实现流畅、智能的语音交互。

### 主要功能
- **实时语音识别（ASR）**：将用户的语音流实时转换为文字
- **智能对话**：对识别出的文字进行理解，并生成回复文本
- **实时语音合成（TTS）**：将回复文本实时合成为语音流
- **完整交互闭环**：录音 -> 识别 -> 对话 -> 合成 -> 播放

## 🏗️ 技术架构

### ESP32客户端 (MicroPython)
- 通过I2S麦克风实时采集音频数据
- 通过WebSocket将音频数据流式传输到中转服务器
- 接收中转服务器下发的音频流，并通过I2S功放播放

### Python中转服务器
- 接收ESP32的WebSocket连接
- 与火山引擎的WebSocket服务建立连接并处理认证逻辑
- 在两条WebSocket连接之间高效、低延迟地双向转发音频数据流

### 火山引擎 (提供PaaS能力)
- 实时语音识别服务
- 对话系统
- 实时语音合成服务

## 📋 硬件准备

### 必需硬件
- **主控**: ESP32-S3开发板（推荐，性能更优）
- **音频输入**: I2S麦克风模块（推荐INMP441，信噪比高）
- **音频输出**: I2S功放模块和扬声器（推荐MAX98357A模块）
- **连接线**: 杜邦线若干

### 接线参考
| 模块名称 | 引脚 | 连接至ESP32-S3 |
|---------|------|---------------|
| INMP441 (麦克风) | SCK | GPIO5 |
| | WS | GPIO6 |
| | SD | GPIO7 |
| MAX98357A (功放) | BCLK | GPIO12 |
| | LRC | GPIO11 |
| | DIN | GPIO13 |
| 通用引脚 | VDD/VIN | 3.3V |
| | GND | GND |

> **注意**: 以上为默认引脚配置，可根据实际情况在代码中修改。

## 🚀 快速开始

### 第一步：准备工作
1. **软件环境**
   - Python 3.7或更高版本
   - MicroPython IDE（推荐Thonny）
   - Git

2. **云服务账号**
   - 访问[火山引擎官网](https://www.volcengine.com/)注册账号
   - 开通相关服务并获取`App-ID`和`Access-Key`

### 第二步：服务器端部署
```bash
# 1. 克隆项目代码
git clone https://github.com/zhou19830318/S2S_doubao_esp32s3_Agent.git
cd S2S_doubao_esp32s3_Agent

# 2. 创建并激活虚拟环境
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. 安装依赖
pip install -r Agent_Server/requirements.txt

# 4. 配置密钥
# 打开 Agent_Server/config.py 文件
# 修改 ws_connect_config 中的 App-ID 和 Access-Key

# 5. 测试API连接
python Agent_Server/local_agent_test.py

# 6. 启动服务器
python Agent_Server/esp32_server.py
```

### 第三步：客户端部署
1. **刷入MicroPython固件**
   - 从[MicroPython官网](https://micropython.org/download/esp32/)下载固件
   - 使用esptool.py刷入ESP32

2. **配置客户端**
   - 使用Thonny IDE连接ESP32
   - 上传`esp32_client.py`到ESP32
   - 修改以下配置：
     ```python
     # 修改Wi-Fi信息
     self.WIFI_SSID, self.WIFI_PASSWORD = "你的WiFi名称", "你的WiFi密码"
     
     # 修改服务器IP地址
     self.SERVER_URL = "ws://192.168.1.6:8765"  # 替换为电脑的局域网IP
     
     # (可选) 修改I2S引脚配置
     ```

3. **运行客户端**
   - 在Thonny中按F5运行代码
   - 观察REPL输出，确认连接成功

## 🔧 联调与验证

成功部署后：
1. **ESP32端**显示：
   ```
   WiFi Connected: 192.168.1.8
   [WS] Handshake successful.
   [System] Connected to server.
   ```

2. **服务器端**显示：
   ```
   [Server] New connection: ...
   ```

3. **测试**：
   - 对着麦克风说"你好"
   - 服务器端开始打印云端会话日志
   - ESP32扬声器播放豆包的回复

## ❓ 常见问题

### 1. ESP32无法连接Wi-Fi
- ✅ 检查`WIFI_SSID`和`WIFI_PASSWORD`是否正确
- ✅ 确保使用2.4GHz Wi-Fi（ESP32对5GHz支持不佳）

### 2. 无法连接服务器
- ✅ 确认`SERVER_URL`中的IP地址是服务器电脑的当前局域网IP
- ✅ 确保ESP32和电脑在同一Wi-Fi网络下
- ✅ 检查防火墙设置，允许8765端口访问

### 3. 没有声音或声音异常
- ✅ 检查I2S引脚接线是否与代码定义一致
- ✅ 确认麦克风和功放模块的VDD和GND连接正确
- ✅ 调试`record_task`，确认能读到音频数据

## 📁 项目结构
```
S2S_doubao_esp32s3_Agent/
├── Agent_Server/
│   ├── config.py          # 服务器配置（密钥等）
│   ├── esp32_server.py    # 主服务器文件
│   ├── local_agent_test.py # API测试文件
│   └── requirements.txt    # Python依赖
├── esp32_client.py        # ESP32客户端主文件
└── README.md              # 项目说明文档
```

## 🎯 扩展功能

基于此项目，你可以进一步探索：
- **自定义唤醒词**：集成轻量级本地唤醒词引擎
- **智能家居控制**：通过语音控制灯光、开关等设备
- **机器人交互**：作为机器人的语音交互中枢
- **多语言支持**：扩展支持更多语言的识别和合成

## 📄 许可证

本项目遵循MIT许可证。详见LICENSE文件。

## 🤝 贡献指南

欢迎提交Issue和Pull Request来改进本项目。

## 🔗 相关链接

- [火山引擎官网](https://www.volcengine.com/)
- [MicroPython官网](https://micropython.org/)
- [Thonny IDE](https://thonny.org/)
- [ESP32官方文档](https://docs.espressif.com/)
