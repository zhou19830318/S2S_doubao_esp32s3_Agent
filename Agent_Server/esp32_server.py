import asyncio
import json
import time
import websockets
import config
from bridge_session import BridgeDialogSession


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


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
        log(f"[Server] New connection: {websocket.remote_address}")
        up_bytes = 0
        down_bytes = 0
        last_up_log = 0
        last_down_log = 0
    
        # 初始化云端会话，显式指定 PCM 格式以匹配 ESP32
        bridge = BridgeDialogSession(
            ws_config=config.ws_connect_config,
            output_audio_format="pcm_s16le"
        )

        async def forward_to_esp32(audio_data):
            """将云端音频全速下发给 ESP32 (依靠 WebSocket 背压)"""
            nonlocal down_bytes, last_down_log
            try:
                if hasattr(websocket, 'open') and not websocket.open:
                    return
                down_bytes += len(audio_data)
                if down_bytes - last_down_log >= 24000:
                    log(f"[Server] To ESP32 {down_bytes // 1024} KB")
                    last_down_log = down_bytes
                await websocket.send(audio_data)
            except websockets.exceptions.ConnectionClosed as e:
                log(f"[Server] Audio forward closed: code={e.code}, reason={e.reason}, down={down_bytes // 1024} KB")
            except Exception as e:
                log(f"[Server] Audio forward error: {e}, down={down_bytes // 1024} KB")

        async def forward_event_to_esp32(event_id, payload):
            asr_text = None
            llm_text = None
            try:
                def walk(obj, asr_keys, llm_keys, found):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if isinstance(v, str):
                                if not found[0] and k in asr_keys:
                                    found[0] = v
                                if not found[1] and k in llm_keys:
                                    found[1] = v
                            else:
                                walk(v, asr_keys, llm_keys, found)
                    elif isinstance(obj, list):
                        for item in obj:
                            walk(item, asr_keys, llm_keys, found)

                if isinstance(payload, dict):
                    found = [None, None]
                    asr_keys = ("asr_text", "user_text", "question", "transcript", "input_text")
                    llm_keys = ("llm_text", "bot_text", "answer", "reply_text", "output_text")
                    walk(payload, asr_keys, llm_keys, found)
                    asr_text, llm_text = found[0], found[1]
            except Exception as e:
                try:
                    log(f"[Server] Event parse error for {event_id}: {e}, payload={payload}")
                except Exception:
                    log(f"[Server] Event parse error for {event_id}: {e}")

            any_text = False
            if asr_text:
                log(f"[ASR] {asr_text}")
                any_text = True
            if llm_text:
                log(f"[LLM] {llm_text}")
                any_text = True
            try:
                if asr_text:
                    if hasattr(websocket, 'open') and not websocket.open:
                        return
                    await websocket.send(json.dumps({"type": "asr", "text": asr_text}))
                if llm_text:
                    if hasattr(websocket, 'open') and not websocket.open:
                        return
                    await websocket.send(json.dumps({"type": "llm", "text": llm_text}))
            except Exception as e:
                log(f"[Server] Text forward error: {e}")
            if not any_text:
                try:
                    log(f"[Server] Event {event_id} payload={json.dumps(payload, ensure_ascii=False)}")
                except Exception:
                    log(f"[Server] Event {event_id} payload={payload}")

            if event_id in [3001, 150]:
                log(f"[Server] Interruption detected (Event {event_id}). Sending stop command.")
                try:
                    if hasattr(websocket, 'open') and not websocket.open:
                        return
                    await websocket.send(json.dumps({"command": "stop"}))
                except Exception as e:
                    log(f"[Server] Stop command error: {e}")

        bridge.on_audio_received = forward_to_esp32
        bridge.on_event_received = forward_event_to_esp32

        try:
            # 1. 建立云端连接
            await bridge.start()
            log("[Server] Cloud bridge session started.")
            
            # 2. 接收来自 ESP32 的音频数据流
            async for message in websocket:
                if isinstance(message, bytes):
                    # 收到 ESP32 的原始音频 (16k, 16bit, Mono)
                    up_bytes += len(message)
                    if up_bytes - last_up_log >= 10240:
                        log(f"[Server] From ESP32 {up_bytes // 1024} KB")
                        last_up_log = up_bytes
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
            log(f"[Server] ESP32 disconnected: {websocket.remote_address}, code={e.code}, reason={e.reason}, up={up_bytes // 1024} KB, down={down_bytes // 1024} KB")
        except Exception as e:
            log(f"[Server] Main loop error: {e}, up={up_bytes // 1024} KB, down={down_bytes // 1024} KB")
        finally:
            await bridge.stop()
            log(f"[Server] Session closed for {websocket.remote_address}")

    async def start(self):
        log(f"[Server] Running on ws://{self.host}:{self.port}")
        async with websockets.serve(self.handle_esp32_connection, self.host, self.port):
            await asyncio.Future()

if __name__ == "__main__":
    server = ESP32WebSocketServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        log("[Server] Stopped")
