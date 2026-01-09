# Rock-Paper-Scissors-Robot

一個基於 Raspberry Pi 5 與 MediaPipe 的剪刀石頭布系統。  
結合電腦視覺、機器學習和嵌入式系統，打造能與人類實時互動對戰的機械手臂機器人。

## 簡介

本專案是一個完整的人機互動系統，展示了從影像辨識、網路通訊到機械控制的整合應用：  

- **Server 端** (`server.py`)：基於 Flask + SocketIO 的後端服務，整合 Google MediaPipe 進行即時手勢辨識與判定  
- **Raspberry Pi 5 端** (`pi.py`)：嵌入式控制系統，負責攝影機擷取、肌腱驅動機械手控制及網路通訊  

##  專案特色

###  技術整合亮點
- **電腦視覺應用**：運用 MediaPipe Hand Tracking 進行 21 個手部關鍵點偵測
- **自訂手勢辨識演算法**：基於手指開合狀態的幾何判斷邏輯（Finger-Up Detection）
- **分散式架構設計**：Client-Server 架構分離運算密集任務與硬體控制
- **即時雙向通訊**：WebSocket 實現低延遲的遊戲觸發機制
- **精確馬達控制**：PWM 控制 5 個 SG90 伺服馬達，模擬真實手部動作
- **肌腱驅動機構**：3D 列印仿生機械手，透過線材牽引實現手指彎曲

### 工程實踐
- 影像前處理與自動存檔系統（deque 循環佇列管理）
- 多執行緒並發處理（避免阻塞主循環）
- 錯誤處理與系統穩定性設計
- 模組化程式架構便於維護擴充

## 系統架構

```
┌─────────────────┐            ┌──────────────────┐
│  Raspberry Pi   │            │   Server (PC)    │
│                 │         　 │                  │
│  • Camera       │────────▶  │  • Flask API      │
│  • ServoKit     │ HTTP       │  • MediaPipe     │
│  • SocketIO     │◀────────  │  • SocketIO       │
└─────────────────┘ WebSocket  └──────────────────┘
```

## 硬體需求

### Raspberry Pi 端
- **主控板**：Raspberry Pi 5（4GB RAM 或以上建議）
- **攝影機**：Picamera2 相容模組（建議 Camera Module 3）
- **馬達驅動**：PCA9685 16 通道 PWM 伺服馬達驅動板
- **伺服馬達**：5 個 SG90 微型伺服馬達（對應五根手指）
- **機械結構**：3D 列印肌腱牽引式機械手
  - 材質建議：PLA 或 PETG
  - 需配備釣魚線或尼龍線作為肌腱
- **電源**：5V 3A 電源供應器（供應伺服馬達）

### Server 端
- **作業系統**：Windows 10/11
- **處理器**：建議 i5 或以上（需執行 MediaPipe 推論）
- **記憶體**：8GB RAM 以上
- **網路**：與 Raspberry Pi 處於同一區域網路

## 軟體需求

### Server 端 (Windows)
```bash
Python 3.9+
flask==3.0.0
flask-socketio==5.3.5
opencv-python==4.8.1.78
mediapipe==0.10.8
numpy==1.24.3
```

### Raspberry Pi 5 端（需使用虛擬環境）
```bash
Python 3.11+
python-socketio[client]==5.10.0
requests==2.31.0
picamera2  # 需從系統套件安裝
adafruit-servokit  # 需從系統套件安裝
Pillow==10.1.0
```

> **重要**：Raspberry Pi 5 需使用**虛擬環境搭配系統套件**的混合模式
> - `picamera2` 和 `adafruit-servokit` 必須安裝在系統 Python 環境
> - 其他套件可在虛擬環境中安裝
> - 建立虛擬環境時需加上 `--system-site-packages` 參數

##  配置說明

### 伺服馬達通道配置 (pi.py)

```python
CHANNEL_INPUT = {
    "thumb": 1,   # 拇指
    "index": 2,   # 食指
    "middle": 3,  # 中指
    "ring": 4,    # 無名指
    "pinky": 5    # 小拇指
}
```

### 伺服馬達角度設定(依據伺服馬達與機械手自訂)

```python
# 彎曲狀態角度
FINGER_ANGLES_BENT = {
    "thumb": x,
    "index": x,
    "middle": x,
    "ring": x,
    "pinky": x
}

# 伸直狀態角度
FINGER_ANGLES_STRAIGHT = {
    "thumb": x,
    "index": x,
    "middle": x,
    "ring": x,
    "pinky": x
}
```

### 手勢辨識參數 (server.py)

```python
MinDetConf = 0.5  # 最小偵測信心值（0.0-1.0）
HANDS = 1         # 偵測手的數量
```

## 使用方式

### 方法一：透過終端控制

1. 啟動 Server 後，在終端輸入：
```bash
SERVER> start
```

2. Raspberry Pi 會自動：
   - 隨機選擇一個手勢
   - 控制機械手做出動作
   - 拍攝玩家的手勢
   - 上傳至 Server 進行辨識
   - 回傳對戰結果

### 方法二：透過 HTTP API

發送 POST 請求到 `/trigger_start`：
```bash
curl -X POST http://YOUR_SERVER_IP:5000/trigger_start
```

### 手動提交影像

```bash
curl -X POST http://YOUR_SERVER_IP:5000/submit \
  -F "image=@your_image.jpg" \
  -F "esp_move=rock"
```

## 專案結構

```
.
├── server.py           # Server 端主程式
├── pi.py              # Raspberry Pi 端主程式
├── raw_input_*.jpg    # 原始輸入影像（最多保存 5 張）
├── processed_*.jpg    # 處理後影像（最多保存 5 張）
└── README.md          # 專案說明文件
```

### 手勢辨識不準確
- 調整 `MinDetConf` 參數（降低值可提高靈敏度）
- 確保光源充足
- 調整攝影機角度，確保手部完整入鏡
- 背景盡量簡潔
- 調整辨別邏輯

## 手勢辨識邏輯

系統辨識三種基本手勢：

| 手勢 | 判斷條件 |
|------|----------|
| 石頭 (rock) | 五指全部彎曲 |
| 布 (paper) | 五指全部伸直 |
| 剪刀 (scissors) | 食指和中指伸直，其餘彎曲 |

辨識採用「最接近匹配」演算法，自動選擇最相似的手勢。

## 待改進

- [ ] 網頁前端儀表板
- [ ] 勝負統計分析與視覺化
- [ ] 音效系統
- [ ] 修繕手勢辨識邏輯
- [ ] 新增其他開始方式
