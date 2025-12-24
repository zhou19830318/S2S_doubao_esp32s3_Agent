import machine
from machine import I2S, Pin
import time
import network
import gc
import ujson as json
import uasyncio as asyncio
from aiohttp import ClientSession

class ESP32RealtimeClient:
    """
    ESP32-S3 实时对话客户端 (暴力硬件缓冲版)
    思路：利用 I2S 硬件自带的超大缓冲区进行背压，取消一切复杂的软件缓冲
    """
    def __init__(self):
        self.I2S_SCK_I, self.I2S_WS_I, self.I2S_SD_I = Pin(5), Pin(6), Pin(7)
        self.I2S_SCK_O, self.I2S_WS_O, self.I2S_SD_O = Pin(12), Pin(11), Pin(13)
        self.WIFI_SSID, self.WIFI_PASSWORDWIF"xxx", "xxx"
        self.SERVER_URL = "ws://192.168.1.6:8765"

        self.is_running = False
        self.ws = None

        self.init_wifi()
        self.init_i2s()

    def init_wifi(self):
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        if not sta.isconnected():
            sta.connect(self.WIFI_SSID, self.WIFI_PASSWORD)
            for _ in range(40):
                if sta.isconnected(): break
                time.sleep(0.5)
        if not sta.isconnected(): machine.reset()
        print("WiFi Connected:", sta.ifconfig()[0])

    def init_i2s(self):
        # 录音 I2S
        self.audio_in = I2S(0, sck=self.I2S_SCK_I, ws=self.I2S_WS_I, sd=self.I2S_SD_I,
            mode=I2S.RX, bits=16, format=I2S.MONO, rate=16000, ibuf=4096)
        # 播放 I2S：申请最大的硬件缓冲区 (64KB)，这相当于在 DMA 层面直接缓冲
        # 这比任何软件 Python 缓冲都要稳定，因为它不受协程调度干扰
        self.audio_out = I2S(1, sck=self.I2S_SCK_O, ws=self.I2S_WS_O, sd=self.I2S_SD_O,
            mode=I2S.TX, bits=16, format=I2S.MONO, rate=24000, ibuf=16384)
        print("I2S HW Buffer: 64KB")

    async def record_task(self):
        read_buf = bytearray(1024)
        while self.is_running:
            try:
                n = self.audio_in.readinto(read_buf)
                if n > 0: await self.ws.send_bytes(read_buf[:n])
                await asyncio.sleep(0)
            except: break

    async def play_and_recv_task(self):
        """核心：将接收和播放合并为一个任务，彻底消除队列和协程切换延迟"""
        print("Combined Play/Recv task started.")
        try:
            async for msg in self.ws:
                if not self.is_running: break
                
                if msg.type == 0x2: # BINARY AUDIO
                    # 收到数据立即同步喂给 I2S 硬件缓冲
                    # 如果 ibuf 满了，write 会自动阻塞并产生 WebSocket 背压
                    self.audio_out.write(msg.data)
                
                elif msg.type == 0x1: # TEXT
                    if "stop" in msg.data:
                        # 停止播放：通过切换模式清空硬件缓冲 (MicroPython 特有技巧)
                        self.audio_out.deinit()
                        self.init_i2s()
                
                # 尽量不在这里做任何耗时操作
                await asyncio.sleep(0)
        except Exception as e:
            print(f"Stream error: {e}")
            self.is_running = False

    async def start(self):
        while True:
            try:
                async with ClientSession() as session:
                    async with session.ws_connect(self.SERVER_URL) as ws:
                        print("Connected.")
                        self.ws = ws
                        self.is_running = True
                        # 仅运行两个核心任务
                        await asyncio.gather(self.record_task(), self.play_and_recv_task())
            except:
                self.is_running = False
                await asyncio.sleep(3)
                gc.collect()

if __name__ == "__main__":
    asyncio.run(ESP32RealtimeClient().start())

