import asyncio
import json
import websockets
import config
from bridge_session import BridgeDialogSession

class ESP32WebSocketServer:
    """
    ESP32 中转服务器
    针对 ESP32 内存有限和网络不稳定的特性进行了专门优化
    """
    def __init__(self, host="0.0.0.0", port=8765):
        self.host = host
        self.port = port

    async def handle_esp32_connection(self, websocket, path=None):
        """处理来自 ESP32 的连接"""
        print(f"[Server] New connection: {websocket.remote_address}")
    
        # 初始化云端会话，显式指定 PCM 格式以匹配 ESP32
        bridge = BridgeDialogSession(
            ws_config=config.ws_connect_config,
            output_audio_format="pcm_s16le"
        )

        async def forward_to_esp32(audio_data):
            """将云端音频全速下发给 ESP32 (依靠 WebSocket 背压)"""
            try:
                if hasattr(websocket, 'open') and not websocket.open:
                    return
                
                # 彻底移除人为延迟和分片，让 TCP 协议栈自动处理流量
                # WebSocket.send 会在底层缓冲区满时自动进行背压控制
                await websocket.send(audio_data)
            except websockets.exceptions.ConnectionClosed as e:
                print(f"[Server] Audio forward closed: code={e.code}, reason={e.reason}")
            except Exception as e:
                print(f"[Server] Audio forward error: {e}")

        async def forward_event_to_esp32(event_id, payload):
            """处理云端业务事件，实现打断功能"""
            # 修正：3001 是火山引擎协议中的 VAD_BEGIN (检测到开始说话)
            # 150 是 ASR 识别过程中的中间状态
            # 只有在这些真正代表用户说话的时刻才发送 stop 指令
            if event_id in [3001, 150]: 
                print(f"[Server] Interruption detected (Event {event_id}). Sending stop command.")
                try:
                    if hasattr(websocket, 'open') and not websocket.open:
                        return
                    await websocket.send(json.dumps({"command": "stop"}))
                except Exception as e:
                    print(f"[Server] Stop command error: {e}")

        bridge.on_audio_received = forward_to_esp32
        bridge.on_event_received = forward_event_to_esp32

        try:
            # 1. 建立云端连接
            await bridge.start()
            print("[Server] Cloud bridge session started.")
            
            # 2. 接收来自 ESP32 的音频数据流
            async for message in websocket:
                if isinstance(message, bytes):
                    # 收到 ESP32 的原始音频 (16k, 16bit, Mono)
                    await bridge.send_audio(message)
                else:
                    # 收到 ESP32 的控制或文本指令
                    try:
                        data = json.loads(message)
                        if data.get("type") == "text":
                            await bridge.send_text(data.get("content"))
                    except:
                        pass

        except websockets.exceptions.ConnectionClosed as e:
            print(f"[Server] ESP32 disconnected: {websocket.remote_address}, code={e.code}, reason={e.reason}")
        except Exception as e:
            print(f"[Server] Main loop error: {e}")
        finally:
            await bridge.stop()
            print(f"[Server] Session closed for {websocket.remote_address}")

    async def start(self):
        print(f"[Server] Running on ws://{self.host}:{self.port}")
        async with websockets.serve(self.handle_esp32_connection, self.host, self.port):
            await asyncio.Future()

if __name__ == "__main__":
    server = ESP32WebSocketServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[Server] Stopped")
