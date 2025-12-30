import machine
from machine import I2S, Pin
import time
import network
import gc
import ujson as json
import uasyncio as asyncio
import ubinascii as binascii
import urandom as random
import ustruct as struct
from neopixel import NeoPixel  # 添加neopixel库


def log(msg):
    t = time.localtime()
    print("[{:02d}:{:02d}:{:02d}] {}".format(t[3], t[4], t[5], msg))


class WebSocket:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.closed = False

    async def send_bytes(self, data):
        await self._send_frame(0x2, data)

    async def _send_frame(self, opcode, data):
        if self.closed: return
        try:
            header = bytearray()
            header.append(0x80 | opcode)
            payload_len = len(data)
            if payload_len <= 125:
                header.append(0x80 | payload_len)
            elif payload_len <= 65535:
                header.append(0x80 | 126)
                header.extend(struct.pack("!H", payload_len))
            else:
                header.append(0x80 | 127)
                header.extend(struct.pack("!Q", payload_len))
            
            mask = bytes(random.getrandbits(8) for _ in range(4))
            header.extend(mask)
            self.writer.write(header)
            masked_data = bytearray(payload_len)
            for i in range(payload_len):
                masked_data[i] = data[i] ^ mask[i % 4]
            self.writer.write(masked_data)
            await self.writer.drain()
        except Exception as e:
            log(f"[WS] Send error: {e}")
            self.closed = True
            raise

    async def _read_exactly(self, n):
        res = bytearray()
        while len(res) < n:
            chunk = await self.reader.read(n - len(res))
            if not chunk: raise EOFError()
            res.extend(chunk)
        return res

    def __aiter__(self):
        return self

    async def __anext__(self):
        while not self.closed:
            try:
                res = await self.reader.read(2)
                if not res or len(res) < 2: break
                opcode = res[0] & 0x0F
                has_mask = res[1] & 0x80
                length = res[1] & 0x7F
                if length == 126:
                    length = struct.unpack("!H", await self._read_exactly(2))[0]
                elif length == 127:
                    length = struct.unpack("!Q", await self._read_exactly(8))[0]
                if has_mask:
                    mask = await self._read_exactly(4)
                payload = await self._read_exactly(length)
                if has_mask:
                    payload = bytearray(payload)
                    for i in range(length):
                        payload[i] ^= mask[i % 4]
                if opcode == 0x8: break
                if opcode == 0x9:
                    await self._send_frame(0xA, payload)
                    continue
                class Msg:
                    def __init__(self, t, d):
                        self.type = t
                        self.data = d
                if opcode == 0x1: 
                    # print(f"[WS] Recv Opcode 0x1 (Text), Len: {length}")
                    return Msg(0x1, payload.decode())
                if opcode == 0x2:
                    return Msg(0x2, payload)
            except Exception as e:
                log(f"[WS] Recv error in __anext__: {e}")
                self.closed = True
                raise
        self.closed = True
        log("[WS] Iterator closed, raising StopAsyncIteration")
        raise StopAsyncIteration

    async def close(self):
        if not self.closed:
            self.closed = True
            try:
                await self._send_frame(0x8, b"")
                self.writer.close()
                await self.writer.wait_closed()
            except: pass

async def connect_ws(url):
    log(f"[WS] Connecting to {url}...")
    proto, _, host_port_path = url.split("/", 2)
    if "/" in host_port_path:
        host_port, path = host_port_path.split("/", 1)
        path = "/" + path
    else:
        host_port, path = host_port_path, "/"
    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host, port = host_port, 80
    
    log(f"[WS] Opening connection to {host}:{port}...")
    reader, writer = await asyncio.open_connection(host, port)
    key = binascii.b2a_base64(bytes(random.getrandbits(8) for _ in range(16)))[:-1].decode()
    header = "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, host, key)
    writer.write(header.encode())
    await writer.drain()
    
    log("[WS] Waiting for handshake response...")
    line = await reader.readline()
    if not line.startswith(b"HTTP/1.1 101"):
        raise Exception("Handshake failed: " + line.decode())
    
    while True:
        line = await reader.readline()
        if line == b"\r\n" or not line: break
    log("[WS] Handshake successful.")
    return WebSocket(reader, writer)


class LEDController:
    """WS2812 LED控制器"""
    def __init__(self, pin_num=9, num_leds=8):
        self.pin = Pin(pin_num, Pin.OUT)
        self.np = NeoPixel(self.pin, num_leds)
        self.num_leds = num_leds
        self.current_state = "idle"
        
        # 颜色定义 (R, G, B)
        self.COLORS = {
            "idle": (0, 0, 0),        # 关闭
            "listening": (255, 150, 0),  # 黄色 (聆听)
            "playing": (0, 255, 0),      # 绿色 (播放)
            "connecting": (0, 0, 255),   # 蓝色 (连接中)
            "error": (255, 0, 0),        # 红色 (错误)
        }
    
    def set_all(self, color_name):
        """设置所有LED为指定颜色"""
        if color_name in self.COLORS:
            self.current_state = color_name
            color = self.COLORS[color_name]
            for i in range(self.num_leds):
                self.np[i] = color
            self.np.write()
    
    def set_breathing(self, color_name, speed=10):
        """呼吸灯效果"""
        if color_name in self.COLORS:
            base_color = self.COLORS[color_name]
            # 简单的呼吸效果实现
            for brightness in range(0, 256, speed):
                color = tuple(int(c * brightness / 255) for c in base_color)
                for i in range(self.num_leds):
                    self.np[i] = color
                self.np.write()
                time.sleep_ms(50)
            for brightness in range(255, -1, -speed):
                color = tuple(int(c * brightness / 255) for c in base_color)
                for i in range(self.num_leds):
                    self.np[i] = color
                self.np.write()
                time.sleep_ms(50)
    
    def set_progress(self, color_name, progress):
        """进度条效果 (0.0到1.0)"""
        if color_name in self.COLORS:
            color = self.COLORS[color_name]
            lit_leds = int(self.num_leds * progress)
            for i in range(self.num_leds):
                if i < lit_leds:
                    self.np[i] = color
                else:
                    self.np[i] = (0, 0, 0)
            self.np.write()
    
    def clear(self):
        """关闭所有LED"""
        self.set_all("idle")


class ESP32RealtimeClient:
    """
    ESP32-S3 实时对话客户端
    思路：利用 I2S 硬件自带的超大缓冲区进行背压，取消一切复杂的软件缓冲
    """
    def __init__(self):
        self.I2S_SCK_I, self.I2S_WS_I, self.I2S_SD_I = Pin(4), Pin(5), Pin(6)
        self.I2S_SCK_O, self.I2S_WS_O, self.I2S_SD_O = Pin(12), Pin(11), Pin(13)
        self.WIFI_SSID, self.WIFI_PASSWORD = "xxx", "xxx"
        self.SERVER_URL = "ws://192.168.2.110:8765"

        self.is_running = False
        self.ws = None
        self.audio_queue = [] # 软件音频队列，用于解耦接收和播放
        
        # 添加LED控制器
        self.leds = LEDController(pin_num=9, num_leds=8)
        self.is_listening = False
        self.is_playing = False

        self.init_wifi()
        self.init_i2s()

    def init_wifi(self):
        try:
            self.leds.set_all("connecting")  # 连接WiFi时显示蓝色
            sta = network.WLAN(network.STA_IF)
            sta.active(True)
            if not sta.isconnected():
                sta.connect(self.WIFI_SSID, self.WIFI_PASSWORD)
                for _ in range(40):
                    if sta.isconnected():
                        break
                    time.sleep(0.5)
            if not sta.isconnected():
                self.leds.set_all("error")  # 连接失败显示红色
                log("[WiFi] Connect failed, resetting board.")
                time.sleep(1)
                machine.reset()
            log("WiFi Connected: {}".format(sta.ifconfig()[0]))
            self.leds.set_all("idle")  # 连接成功恢复空闲状态
        except Exception as e:
            self.leds.set_all("error")  # 异常时显示红色
            log(f"[WiFi] Internal error: {e}, resetting board.")
            time.sleep(1)
            machine.reset()

    def init_i2s(self):
        # 录音 I2S
        self.audio_in = I2S(0, sck=self.I2S_SCK_I, ws=self.I2S_WS_I, sd=self.I2S_SD_I,
            mode=I2S.RX, bits=16, format=I2S.MONO, rate=16000, ibuf=4096)
        # 播放 I2S：申请最大的硬件缓冲区 (64KB)，这相当于在 DMA 层面直接缓冲
        # 这比任何软件 Python 缓冲都要稳定，因为它不受协程调度干扰
        self.audio_out = I2S(1, sck=self.I2S_SCK_O, ws=self.I2S_WS_O, sd=self.I2S_SD_O,
            mode=I2S.TX, bits=16, format=I2S.MONO, rate=24000, ibuf=16384)
        log("I2S HW Buffer: 64KB")

    async def record_task(self):
        read_buf = bytearray(1024)
        total_sent = 0
        last_log_sent = 0
        log("[Record] Task started.")
        while self.is_running:
            try:
                if not self.is_listening:
                    self.is_listening = True
                    self.is_playing = False
                    self.leds.set_all("listening")  # 开始聆听时亮黄灯
                
                n = self.audio_in.readinto(read_buf)
                if n > 0: 
                    await self.ws.send_bytes(read_buf[:n])
                    total_sent += n
                    # Log every 10KB
                    if total_sent - last_log_sent >= 10240:
                        free_kb = gc.mem_free() // 1024
                        log(f"[Record] Sent {total_sent // 1024} KB, free={free_kb} KB")
                        last_log_sent = total_sent
                else:
                    # 如果没有数据可读，可能停止聆听状态
                    if self.is_listening and len(self.audio_queue) > 0:
                        self.is_listening = False
                        self.leds.set_all("idle")
                
                await asyncio.sleep(0)
            except Exception as e:
                free_kb = gc.mem_free() // 1024
                log(f"[Record] Error: {e}, free={free_kb} KB")
                self.is_running = False
                self.leds.set_all("error")
                break

    async def recv_task(self):
        """仅负责接收 WebSocket 数据，保证打断指令能被立即处理"""
        log("[Recv] Task started.")
        try:
            async for msg in self.ws:
                if not self.is_running: break
                
                if msg.type == 0x2: # BINARY AUDIO
                    # 将音频放入队列，不阻塞接收循环
                    self.audio_queue.append(msg.data)
                    
                    # 如果开始收到音频数据，切换到播放状态
                    if not self.is_playing and len(self.audio_queue) > 0:
                        self.is_playing = True
                        self.is_listening = False
                        self.leds.set_all("playing")  # 开始播放时亮绿灯
                    
                    # 限制队列长度防止内存溢出 (约 2s 的音频)
                    if len(self.audio_queue) > 40:
                        self.audio_queue.pop(0)
                
                elif msg.type == 0x1: # TEXT
                    print(f"[WS Text Raw] {msg.data}") # 必须打印！
                    try:
                        data = json.loads(msg.data)
                        # 处理结构化消息
                        if isinstance(data, dict):
                            msg_type = data.get("type")
                            if msg_type == "asr":
                                print(f"\n[User] {data.get('text')}")
                            elif msg_type == "llm":
                                print(f"\n[Doubao] {data.get('text')}")
                            
                            # 处理打断指令 (兼容合并后的消息)
                            if data.get("command") == "stop":
                                log("[Play] Stop command received!")
                                self.audio_queue.clear()
                                self.is_playing = False
                                self.leds.set_all("idle")  # 停止播放
                                self.audio_out.deinit()
                                self.init_i2s()
                        else:
                            log(f"[Msg JSON] {data}")
                    except Exception as e:
                        log(f"[Msg Parse Error] {e}: {msg.data}")
                        if "stop" in msg.data:
                            self.audio_queue.clear()
                            self.is_playing = False
                            self.leds.set_all("idle")  # 停止播放
                            self.audio_out.deinit()
                            self.init_i2s()
                else:
                    log(f"[WS Recv Other] Type: {msg.type}")
                
                # 检查队列状态，如果队列为空且不在聆听状态，恢复空闲
                if len(self.audio_queue) == 0 and not self.is_listening:
                    self.is_playing = False
                    self.leds.set_all("idle")
                
                if self.audio_queue and len(self.audio_queue) % 20 == 0:
                    free_kb = gc.mem_free() // 1024
                    log(f"[Recv] Queue={len(self.audio_queue)}, free={free_kb} KB")
                
                await asyncio.sleep(0)
        except Exception as e:
            free_kb = gc.mem_free() // 1024
            log(f"[Recv] Error: {e}, free={free_kb} KB")
            self.is_running = False
            self.leds.set_all("error")
        finally:
            log(f"[Recv] Task finished, ws.closed={self.ws.closed if self.ws else None}")
            self.is_running = False
            self.leds.set_all("error")

    async def play_task(self):
        """仅负责从队列取数据并喂给 I2S 硬件"""
        log("[Play] Task started.")
        total_played = 0
        last_log_played = 0
        while self.is_running:
            try:
                if self.audio_queue:
                    data = self.audio_queue.pop(0)
                    # write 会在硬件缓冲区满时自动阻塞
                    self.audio_out.write(data)
                    total_played += len(data)
                    
                    # 显示播放进度
                    if len(self.audio_queue) > 0:
                        progress = 1.0 - (len(self.audio_queue) / 40.0)  # 假设最大队列为40
                        self.leds.set_progress("playing", progress)
                    
                    if total_played - last_log_played >= 24000:
                        free_kb = gc.mem_free() // 1024
                        log(f"[Play] Played {total_played // 1024} KB, free={free_kb} KB")
                        last_log_played = total_played
                else:
                    # 队列为空时，如果没有在聆听，恢复空闲状态
                    if not self.is_listening and self.is_playing:
                        self.is_playing = False
                        self.leds.set_all("idle")
                
                # 无论是否播放了音频，都必须让出 CPU，否则 recv_task 会被饿死
                await asyncio.sleep(0) 
            except Exception as e:
                free_kb = gc.mem_free() // 1024
                log(f"[Play] Error: {e}, free={free_kb} KB")
                self.leds.set_all("error")
                break

    async def start(self):
        while True:
            log(f"[System] Free memory: {gc.mem_free() / 1024:.1f} KB")
            try:
                self.leds.set_all("connecting")  # 连接服务器时显示蓝色
                self.init_wifi()
                ws = await connect_ws(self.SERVER_URL)
                log("[System] Connected to server.")
                self.ws = ws
                self.is_running = True
                self.audio_queue.clear()
                self.leds.set_all("idle")  # 连接成功恢复空闲
                
                # 运行三个核心任务：录音、接收、播放
                await asyncio.gather(
                    self.record_task(), 
                    self.recv_task(),
                    self.play_task()
                )
            except Exception as e:
                log(f"[System] Connection error: {e}")
                self.is_running = False
                self.leds.set_all("error")  # 错误时显示红色
                if self.ws:
                    await self.ws.close()
                    self.ws = None
                log("[System] Retrying in 3 seconds...")
                await asyncio.sleep(3)
                gc.collect()

if __name__ == "__main__":
    # 初始化时显示连接状态
    client = ESP32RealtimeClient()
    # 启动前显示呼吸灯效果
    for _ in range(2):  # 呼吸2次
        client.leds.set_breathing("connecting", speed=20)
    asyncio.run(client.start())


