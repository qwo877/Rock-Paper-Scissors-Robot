from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import cv2
import mediapipe as mp
import numpy as np
import io
import time
import threading
import os
from collections import deque
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# ---------- 基本設定 ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    ping_timeout=120,   
    ping_interval=20   
)

# ---------- 影像保存設定 ----------
SAVE_IMG = True
DIR = "./"   
PREFIX = "raw_input"
PREFIX_1 = "processed"
MAX_IMG = 5

img_q = deque(maxlen=MAX_IMG)
img_q1 = deque(maxlen=MAX_IMG)

# ---------- MP 參數 ----------
MinDetConf = 0.5
HANDS = 1
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# ---------- 核心判斷邏輯 ----------

def getFingersUpLM(flat_lm, handedness="Right"):
    """
    判斷五根手指的開合狀態 (True=伸直, False=彎曲)
    Index: [0]=Thumb, [1]=Index, [2]=Middle, [3]=Ring, [4]=Pinky
    """
    if flat_lm is None or len(flat_lm) < 63:
        return [False] * 5
    fingers = []
    tip_x = flat_lm[4 * 3]
    mcp_x = flat_lm[2 * 3]
    
    if handedness == "Right":
        thumb_up = tip_x > mcp_x 
    else: 
        thumb_up = tip_x < mcp_x
    fingers.append(thumb_up)

    tip_ids = [8, 12, 16, 20]
    pip_ids = [6, 10, 14, 18]
    
    for tip_id, pip_id in zip(tip_ids, pip_ids):
        tip_y = flat_lm[tip_id * 3 + 1]
        pip_y = flat_lm[pip_id * 3 + 1]
        fingers.append(tip_y < pip_y)

    return fingers

def closest(fingers):
    
    # 標準
    patterns = {
        "rock":     [False, False, False, False, False], # 全握
        "paper":    [True,  True,  True,  True,  True],  # 全開
        "scissors": [False, True,  True,  False, False]  # 食中指開
    }
    
    best_match = "rock"
    min_diff = 6
    
    for gesture, pattern in patterns.items():
        diff = sum(1 for f, p in zip(fingers, pattern) if f != p)
        
        if diff < min_diff:
            min_diff = diff
            best_match = gesture
            
    return best_match

def win(player, pi):
    if player == "none": return "no_player_detected"
    if player == pi: return "draw"
    beats = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    return "win" if beats[player] == pi else "lose"

# ---------- 影像處理與存檔 ----------

def save_img1(image_bgr, results):
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{PREFIX_1}_{ts}.jpg"
    path = os.path.join(DIR, filename)
    draw_img = image_bgr.copy()

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(draw_img, hand_landmarks, mp_hands.HAND_CONNECTIONS)

    cv2.imwrite(path, draw_img)
    img_q1.append(path)
    while len(img_q1) > MAX_IMG:
        old = img_q1.popleft()
        if os.path.exists(old): os.remove(old)

def save_img(image_bgr):
    if not SAVE_IMG: return
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(DIR, f"{PREFIX}_{ts}.jpg")
    cv2.imwrite(path, image_bgr)
    img_q.append(path)
    while len(img_q) > MAX_IMG:
        old = img_q.popleft()
        if os.path.exists(old): os.remove(old)

def detectRPSBGR(image_bgr):
    img_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    with mp_hands.Hands(
        static_image_mode=True,
        max_num_hands=HANDS,
        min_detection_confidence=MinDetConf
    ) as hands:

        results = hands.process(img_rgb)
        save_img1(image_bgr, results)

        if not results.multi_hand_landmarks:
            return "none"

        hand_landmarks = results.multi_hand_landmarks[0]
        lm = []
        for lmpt in hand_landmarks.landmark:
            lm.extend([lmpt.x, lmpt.y, lmpt.z])

        try:
            handedness = results.multi_handedness[0].classification[0].label
        except:
            handedness = "Right"

        fingers = getFingersUpLM(lm, handedness)
        gesture = closest(fingers)
        return gesture

# ---------- 終端與API ----------

def cmdListener():
    print("=== SERVER 控制台===")
    print("輸入 'start' 啟動，'exit' 關閉")
    while True:
        try:
            cmd = input("SERVER> ").strip().lower()
            if cmd == "start":
                rid = str(int(time.time()))
                socketio.emit('start', {'round_id': rid, 'timestamp': time.time()})
                print(f"[Broadcast] Round {rid} started.")
            elif cmd in ("exit", "quit"):
                os._exit(0)
        except EOFError: break

@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@app.route('/submit', methods=['POST'])
def submit():
    if 'image' not in request.files:
        return jsonify({'error':'no image'}), 400
    
    f = request.files['image']
    esp_move = request.form.get('esp_move', None)
    
    data = f.read()
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({'error':'decode fail'}), 400

    save_img(img)

    player_move = detectRPSBGR(img)
    result = win(player_move, esp_move)

    resp = {
        'player_move': player_move,
        'esp_move': esp_move,
        'result': result
    }
    
    print(f"[{time.strftime('%H:%M:%S')}] Result: Player({player_move}) vs ESP({esp_move}) -> {result}")
    return jsonify(resp), 200

@app.route('/trigger_start', methods=['POST', 'GET'])
def trigger_start():
    rid = str(int(time.time()))
    socketio.emit('start', {'round_id': rid, 'timestamp': time.time()})
    return jsonify({'status':'ok','round_id':rid}), 200

if __name__ == '__main__':
    t = threading.Thread(target=cmdListener, daemon=True)
    t.start()
    socketio.run(app, host='0.0.0.0', port=5000)
