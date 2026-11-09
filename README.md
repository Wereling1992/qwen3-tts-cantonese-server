# Qwen3-TTS Cantonese Server

[![GitHub](https://img.shields.io/badge/GitHub-Wereling1992%2Fqwen3--tts--cantonese--server-blue?logo=github)](https://github.com/Wereling1992/qwen3-tts-cantonese-server)
[![Docker Pulls](https://img.shields.io/docker/pulls/wereling1992/qwen3-tts-cantonese)](https://hub.docker.com/r/wereling1992/qwen3-tts-cantonese)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

CPU-only **Hong Kong Cantonese** Text-to-Speech server with an OpenAI-compatible API (`POST /v1/audio/speech`).

- **Model**: [jmtl/hk-cantonese-cc0-qwen3-tts-GGUF](https://huggingface.co/jmtl/hk-cantonese-cc0-qwen3-tts-GGUF) (v0.0.5)
- **Runtime**: [Danmoreng/qwen3-tts.cpp](https://github.com/Danmoreng/qwen3-tts.cpp)
- **Endpoint**: `POST /v1/audio/speech`
- **Port**: `3430`
- **Auth**: API Key
- **Long text**: auto-chunked (≤ 45 characters)

**GitHub:** https://github.com/Wereling1992/qwen3-tts-cantonese-server  
**Docker Hub:** [`wereling1992/qwen3-tts-cantonese`](https://hub.docker.com/r/wereling1992/qwen3-tts-cantonese)

---

## Quick Start (recommended: pull the image)

```bash
docker run -d \
  --name qwen3-tts-cantonese \
  -p 3430:3430 \
  -e API_KEY=MySuperSafeKey \
  -v qwen3-tts-models:/models \
  --restart unless-stopped \
  wereling1992/qwen3-tts-cantonese:latest
```

The first start downloads the model (~2.3 GB) into the volume. Later starts reuse it.

### Health check

```bash
curl http://localhost:3430/health
```

### Synthesize speech

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

## docker compose (local build)

```bash
git clone https://github.com/Wereling1992/qwen3-tts-cantonese-server.git
cd qwen3-tts-cantonese-server

export API_KEY=MySuperSafeKey
docker compose up -d --build
```

---

## Push to Docker Hub

```bash
docker login

# Option 1: helper script
./scripts/push-to-dockerhub.sh 1.0.0

# Option 2: manual
docker build -t wereling1992/qwen3-tts-cantonese:latest .
docker push wereling1992/qwen3-tts-cantonese:latest
```

**Recommended: buildx for linux/amd64 (most cloud hosts):**

```bash
docker buildx create --use --name multi 2>/dev/null || docker buildx use multi
docker buildx build --platform linux/amd64 \
  -t wereling1992/qwen3-tts-cantonese:latest \
  --push .
```

> Build takes a while (C++ compilation). Use a machine with enough CPU and memory.

---

## API

### `POST /v1/audio/speech`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | `hk-cantonese-cc0` | Any string (for compatibility) |
| `input` | string | **required** | Text to synthesize (colloquial Cantonese works best) |
| `voice` | string | `hk_voice_343` | Only this baked speaker is supported |
| `response_format` | string | `wav` | `wav` / `mp3` / `pcm` |
| `speed` | float | `1.0` | 0.5–2.0 (best-effort) |
| `seed` | int | `20260905` | Reproducible output |
| `temperature` | float | `0.9` | Keep the default; too low can loop |

**Auth** (either works):
- `x-api-key: <key>`
- `Authorization: Bearer <key>`

### Other endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check (no auth) |
| `GET /v1/models` | List models |
| `GET /v1/voices` | List voices |

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `changeme` | API key (**change this**) |
| `REQUIRE_API_KEY` | `1` | Set to `0` to disable auth |
| `SPEAKER` | `hk_voice_343` | Built-in speaker name |
| `DEFAULT_SEED` | `20260905` | Default random seed |
| `N_THREADS` | `0` | CPU threads (`0` = auto) |
| `MAX_CHARS_PER_CHUNK` | `45` | Auto-chunk size |
| `PORT` | `3430` | Listen port |

---

## Model notes

From the official model card:

- **Chunking**: This server auto-splits on `，。：；！？`, max ~45 characters per chunk.
- **Sampling**: Keep default temperature ≈ 0.9. Greedy / very low temperature can loop.
- **Language**: Colloquial Cantonese works best; written Chinese mispronounces more often.
- **Voice clone**: This GGUF uses a **baked speaker** — reference-audio cloning is **not** supported.

---

## Project layout

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

## License

- Server code: Apache-2.0
- Underlying model: Apache-2.0 + voice under CC-0
- Follow the model card’s responsible-use guidance (do not use for impersonation of real people, etc.)
