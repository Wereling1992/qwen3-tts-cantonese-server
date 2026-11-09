# Qwen3-TTS Cantonese Server

[![GitHub](https://img.shields.io/badge/GitHub-Wereling1992%2Fqwen3--tts--cantonese--server-blue?logo=github)](https://github.com/Wereling1992/qwen3-tts-cantonese-server)
[![Docker Pulls](https://img.shields.io/docker/pulls/wereling1992/qwen3-tts-cantonese)](https://hub.docker.com/r/wereling1992/qwen3-tts-cantonese)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

香港粵語 **CPU-only** Text-to-Speech 服務，提供 OpenAI 兼容 API（`POST /v1/audio/speech`）。

- **Model**: [jmtl/hk-cantonese-cc0-qwen3-tts-GGUF](https://huggingface.co/jmtl/hk-cantonese-cc0-qwen3-tts-GGUF) (v0.0.5)
- **Runtime**: [Danmoreng/qwen3-tts.cpp](https://github.com/Danmoreng/qwen3-tts.cpp)
- **Endpoint**: `POST /v1/audio/speech`
- **Port**: `3430`
- **Auth**: API Key
- **長文本**: 自動斷句（≤ 45 字）

**GitHub:** https://github.com/Wereling1992/qwen3-tts-cantonese-server  
**Docker Hub:** [`wereling1992/qwen3-tts-cantonese`](https://hub.docker.com/r/wereling1992/qwen3-tts-cantonese)

---

## Quick Start（推薦：直接 pull）

```bash
docker run -d \
  --name qwen3-tts-cantonese \
  -p 3430:3430 \
  -e API_KEY=MySuperSafeKey \
  -v qwen3-tts-models:/models \
  --restart unless-stopped \
  wereling1992/qwen3-tts-cantonese:latest
```

首次啟動會自動下載模型（約 2.3 GB），之後會緩存在 volume `qwen3-tts-models`。

### 健康檢查

```bash
curl http://localhost:3430/health
```

### 合成語音

```bash
curl -X POST http://localhost:3430/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "x-api-key: MySuperSafeKey" \
  -d '{
    "model": "hk-cantonese-cc0",
    "input": "今日天氣好好，我哋出去行下街啦。",
    "voice": "hk_voice_343",
    "response_format": "wav"
  }' \
  --output out.wav
```

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:3430/v1",
    api_key="MySuperSafeKey",
)

with client.audio.speech.with_streaming_response.create(
    model="hk-cantonese-cc0",
    voice="hk_voice_343",
    input="今日天氣好好，我哋出去行下街啦。",
    response_format="wav",
) as response:
    response.stream_to_file("out.wav")
```

---

## docker compose（本機開發 / 自建）

```bash
git clone https://github.com/Wereling1992/qwen3-tts-cantonese-server.git
cd qwen3-tts-cantonese-server

export API_KEY=MySuperSafeKey
docker compose up -d --build
```

---

## 推送到 Docker Hub

```bash
docker login

# 方法 1：用腳本
./scripts/push-to-dockerhub.sh 1.0.0

# 方法 2：手動
docker build -t wereling1992/qwen3-tts-cantonese:latest .
docker push wereling1992/qwen3-tts-cantonese:latest
```

**推薦：用 buildx 出 amd64（大多數雲端主機）：**

```bash
docker buildx create --use --name multi 2>/dev/null || docker buildx use multi
docker buildx build --platform linux/amd64 \
  -t wereling1992/qwen3-tts-cantonese:latest \
  --push .
```

> 建置時間較長（要編譯 C++），建議用有足夠 CPU / 記憶體的機器。

---

## API

### `POST /v1/audio/speech`

| 欄位 | 類型 | 預設 | 說明 |
|------|------|------|------|
| `model` | string | `hk-cantonese-cc0` | 任意字串（兼容用） |
| `input` | string | **必填** | 要合成的文字（建議口語粵語） |
| `voice` | string | `hk_voice_343` | 目前只支援這一個 baked speaker |
| `response_format` | string | `wav` | `wav` / `mp3` / `pcm` |
| `speed` | float | `1.0` | 0.5–2.0（best-effort） |
| `seed` | int | `20260905` | 可重現結果 |
| `temperature` | float | `0.9` | 建議保持預設，太低容易 loop |

**認證**（二選一）：
- `x-api-key: <key>`
- `Authorization: Bearer <key>`

### 其他端點

| 端點 | 說明 |
|------|------|
| `GET /health` | 健康檢查（無需認證） |
| `GET /v1/models` | 列出模型 |
| `GET /v1/voices` | 列出聲音 |

---

## 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `API_KEY` | `changeme` | API 金鑰（**請一定要改**） |
| `REQUIRE_API_KEY` | `1` | 設為 `0` 可關閉認證 |
| `SPEAKER` | `hk_voice_343` | 模型內建 speaker 名稱 |
| `DEFAULT_SEED` | `20260905` | 預設隨機種子 |
| `N_THREADS` | `0` | CPU 線程數（0 = 自動） |
| `MAX_CHARS_PER_CHUNK` | `45` | 自動斷句最大字數 |
| `PORT` | `3430` | 監聽埠 |

---

## 模型注意事項

來自官方模型卡：

- **自動斷句**：本服務已內建按 `，。：；！？` 斷句，單段 ≤ 45 字。
- **採樣**：保持預設 temperature ≈ 0.9，避免 greedy。
- **語言**：口語粵語效果最好；書面語容易讀錯。
- **Voice clone**：此 GGUF 是 baked speaker，**不支援** reference audio 克隆。

---

## 專案結構

```
qwen3-tts-cantonese-server/
├── Dockerfile
├── docker-compose.yml
├── server.py                 # FastAPI OpenAI-compatible server
├── requirements.txt
├── LICENSE
├── README.md
└── scripts/
    ├── entrypoint.sh         # Auto-download models on first start
    └── push-to-dockerhub.sh  # Build & push helper
```

---

## 授權

- 本服務程式碼：Apache-2.0
- 底層模型：Apache-2.0 + 聲音為 CC-0
- 使用時請遵守模型卡的 responsible use 指引（勿用作假冒真實人物等）
