import socketio
import requests
import random
import time
import threading
import io
import argparse
from picamera2 import Picamera2
from adafruit_servokit import ServoKit
from PIL import Image

# --------------------- 設定區 ---------------------
CHANNEL_INPUT = {
    "thumb": 1,   # 拇指 
    "index": 2,   # 食指 
    "middle": 3,  # 中指 
    "ring": 4,    # 無名指 
    "pinky": 5    # 小拇指 
}

INVERT_FINGER = {
    "thumb": False,
    "index": False,
    "middle": False,
    "ring": False,
    "pinky": False
}

FINGER_ANGLES_BENT = {
    "thumb": 0,
    "index": 0,
    "middle": 0,
    "ring": 0,
    "pinky": 0
}

FINGER_ANGLES_STRAIGHT = {
    "thumb": 90,
    "index": 90,
    "middle": 120,
    "ring": 120,
    "pinky": 120
}

SERVO_CHANNELS_TOTAL = 16

# -------------------------------------------------

kit = None
servo_lock = threading.Lock()

def init_servos():
    global kit
    try:
        kit = ServoKit(channels=SERVO_CHANNELS_TOTAL)
        print("[Servo] ServoKit 初始化完成")
    except Exception as e:
        print(f"[Servo] ServoKit 初始化失敗，改為模擬模式: {e}")
        kit = None

def user_channel_to_kit_channel(user_ch):
    """把使用者給的 1-based channel 轉為 0-based 並驗證範圍"""
    if user_ch is None:
        return None
    try:
        ch = int(user_ch)
        if ch < 0 or ch >= SERVO_CHANNELS_TOTAL:
            print(f"[Servo] 警告：通道 {user_ch} 越界 (0..{SERVO_CHANNELS_TOTAL-1})")
        return ch
    except:
        return None

def set_servo_angle_raw(ch, angle):
    """低階設角度：如果 kit 為 None 則印模擬訊息"""
    if ch is None:
        print(f"[Servo] Channel 為 None，跳過 (angle={angle})")
        return
    if kit is None:
        print(f"[Servo][SIM] channel {ch} <- {angle}°")
        return
    try:
        if angle is None:
            print(f"[Servo] 要設的角度為 None，channel {ch} 跳過")
            return
        a = max(0, min(180, int(angle)))
        kit.servo[ch].angle = a
    except Exception as e:
        print(f"[Servo] 設定 channel {ch} 角度失敗: {e}")

def set_finger_angle(finger, angle):
    user_ch = CHANNEL_INPUT.get(finger)
    ch = user_channel_to_kit_channel(user_ch)
    if ch is None:
        print(f"[Servo] 找不到 finger {finger} 的 channel")
        return
    if INVERT_FINGER.get(finger, False) and angle is not None:
        angle = 180 - angle
    set_servo_angle_raw(ch, angle)

def control_hand(esp_move):
    if esp_move == "rock":
        states = {f: "bent" for f in CHANNEL_INPUT.keys()}
    elif esp_move == "paper":
        states = {f: "straight" for f in CHANNEL_INPUT.keys()}
    elif esp_move == "scissors":
        states = {f: "bent" for f in CHANNEL_INPUT.keys()}
        states["index"] = "straight"
        states["middle"] = "straight"
    else:
        print(f"[Servo] 未知手勢: {esp_move}")
        return

    # 送出命令（加鎖）
    with servo_lock:
        for finger, state in states.items():
            if state == "straight":
                angle = FINGER_ANGLES_STRAIGHT.get(finger)
            else:
                angle = FINGER_ANGLES_BENT.get(finger)
            print(f"[Servo] ({finger}) -> {state} -> 角度 {angle} (invert={INVERT_FINGER.get(finger)})")
            set_finger_angle(finger, angle)
            time.sleep(0.04)

# --------------------- SocketIO / Camera / Main logic ---------------------
SERVER_URL = 'http://xxx.xxx.xxx.xxx:5000'
SUBMIT_ENDPOINT = f"{SERVER_URL}/submit"

is_processing = False
picam2 = None

sio = socketio.Client(reconnection=True, reconnection_attempts=5, reconnection_delay=1,
                      logger=False, engineio_logger=False)

def init_camera():
    global picam2
    print("[System] 初始化 Picamera2...")
    try:
        picam2 = Picamera2()
        config = picam2.create_still_configuration(
            main={"size": (640, 480), "format": "RGB888"},
            buffer_count=2
        )
        picam2.configure(config)
        picam2.start()
        time.sleep(2)
        # 測試捕捉
        arr = picam2.capture_array()
        if arr is None or arr.size == 0:
            print("[System] 注意：相機測試擷取失敗")
        print("[System] 相機初始化完成")
        return True
    except Exception as e:
        print(f"[Critical] 相機初始化失敗: {e}")
        return False

def run_round_logic(round_id):
    global is_processing
    try:
        print(f"[Logic] 回合 {round_id} 開始")
        esp_move = random.choice(["rock", "paper", "scissors"])
        print(f"[Logic] 選擇動作(測試): {esp_move}")

        # 控制伺服
        control_hand(esp_move)

        # 擷取畫面
        frame = picam2.capture_array()
        if frame is None or frame.size == 0:
            print("[Error] 相機擷取失敗，略過上傳")
            return
        image = Image.fromarray(frame)
        image = image.resize((320, 240), Image.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=70)

        files = {"image": ("frame.jpg", buf.getvalue(), "image/jpeg")}
        data = {"esp_move": esp_move, "round_id": round_id}

        try:
            r = requests.post(SUBMIT_ENDPOINT, files=files, data=data, timeout=5)
            print(f"[Result] Server 回傳狀態: {r.status_code}，內容: {r.text[:200]}")
        except requests.exceptions.RequestException as e:
            print(f"[Error] HTTP 請求失敗: {e}")

    except Exception as e:
        print(f"[Critical] run_round_logic 發生例外: {e}")
    finally:
        is_processing = False
        print(f"[Logic] 回合 {round_id} 結束")

@sio.on("start")
def on_start(data):
    global is_processing
    round_id = data.get("round_id", "unknown")
    print(f"[SocketIO] 收到 start: {round_id}")
    if is_processing:
        print("[Skip] 上一回合尚未結束")
        return
    is_processing = True
    t = threading.Thread(target=run_round_logic, args=(round_id,), daemon=True)
    t.start()

@sio.event
def connect():
    print("[SocketIO] 連線成功")

@sio.event
def disconnect():
    print("[SocketIO] 斷線")

# ---------- 校正 ----------
def calibrate_sequence():
    seq = [("paper", 2.0), ("rock", 2.0), ("scissors", 2.0)]
    print("測試開始")
    for gesture, wait in seq:
        control_hand(gesture)
        time.sleep(wait)
    print("測試結束")

# -------------------- 主邏輯 --------------------
def main(args):
    init_servos()
    if args.calibrate:
        calibrate_sequence()
        return
    if not init_camera():
        print("[System] 相機初始化失敗，程式結束")
        return

    try:
        sio.connect(SERVER_URL, transports=["websocket"])
        sio.wait()
    except KeyboardInterrupt:
        print("\n[System] 使用者中斷")
    except Exception as e:
        print(f"[System] 連線錯誤: {e}")
    finally:
        if picam2:
            picam2.stop()
            picam2.close()
        sio.disconnect()
        print("[System] 程式結束")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true", help="執行伺服校正序列（paper/rock/scissors）")
    args = parser.parse_args()
    main(args)

