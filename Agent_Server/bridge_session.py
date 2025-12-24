import asyncio
import json
import uuid
from typing import Dict, Any, Optional

import config
from realtime_dialog_client import RealtimeDialogClient

class BridgeDialogSession:
    """
    中转对话会话类，将 RealtimeDialogClient 与外部网络流（如 ESP32）解耦。
    不再直接操作 PyAudio 或本地文件，而是通过回调或队列处理音频输入输出。
    """
    def __init__(self, ws_config: Dict[str, Any], output_audio_format: str = "pcm", 
                 mod: str = "audio", recv_timeout: int = 10):
        self.session_id = str(uuid.uuid4())
        self.client = RealtimeDialogClient(
            config=ws_config, 
            session_id=self.session_id,
            output_audio_format=output_audio_format, 
            mod=mod, 
            recv_timeout=recv_timeout
        )
        self.is_running = False
        self.is_session_finished = False
        self.on_audio_received = None  # 回调函数: func(audio_data: bytes)
        self.on_event_received = None  # 回调函数: func(event_id: int, payload: dict)

    async def start(self):
        """建立云端连接"""
        await self.client.connect()
        self.is_running = True
        # 启动接收循环
        asyncio.create_task(self._receive_loop())

    async def send_audio(self, pcm_data: bytes):
        """转发音频到云端"""
        if self.is_running:
            await self.client.task_request(pcm_data)

    async def send_text(self, text: str):
        """转发文本到云端"""
        if self.is_running:
            await self.client.chat_text_query(text)

    async def stop(self):
        """停止会话"""
        self.is_running = False
        await self.client.finish_session()
        # 等待云端确认结束（简单处理，实际可增加 Event 监听）
        await asyncio.sleep(0.5)
        await self.client.finish_connection()
        await self.client.close()

    async def _receive_loop(self):
        """持续接收云端响应并触发回调"""
        try:
            while self.is_running:
                response = await self.client.receive_server_response()
                if not response:
                    continue

                msg_type = response.get('message_type')
                
                # 1. 处理音频数据 (SERVER_ACK 携带音频)
                if msg_type == 'SERVER_ACK' and isinstance(response.get('payload_msg'), bytes):
                    if self.on_audio_received:
                        await self.on_audio_received(response['payload_msg'])
                
                # 2. 处理业务事件 (SERVER_FULL_RESPONSE)
                elif msg_type == 'SERVER_FULL_RESPONSE':
                    event = response.get('event')
                    payload = response.get('payload_msg', {})
                    if self.on_event_received:
                        await self.on_event_received(event, payload)
                    
                    # 检查会话是否结束
                    if event in [152, 153]:
                        self.is_session_finished = True
                        break
                
                elif msg_type == 'SERVER_ERROR':
                    print(f"Cloud Server Error: {response.get('payload_msg')}")
                    break

        except Exception as e:
            print(f"Bridge receive loop error: {e}")
        finally:
            self.is_running = False
            self.is_session_finished = True
