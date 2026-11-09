#!/usr/bin/env python3
"""
Qwen3-TTS Cantonese OpenAI-compatible Server (CPU-only)

POST /v1/audio/speech
Uses Danmoreng/qwen3-tts.cpp + jmtl/hk-cantonese-cc0-qwen3-tts-GGUF
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import psutil
import soundfile as sf
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
MODELS_DIR = Path(os.environ.get("MODELS_DIR", "/models"))
TALKER_DIR = MODELS_DIR / "talker"
CODEC_PATH = MODELS_DIR / "qwen-tokenizer-12hz-q8_0.gguf"
CLI_BIN = Path(os.environ.get("QWEN3_TTS_CLI", "/usr/local/bin/qwen3-tts-cli"))

SPEAKER = os.environ.get("SPEAKER", "hk_voice_343")
DEFAULT_SEED = int(os.environ.get("DEFAULT_SEED", "20260905"))
N_THREADS = int(os.environ.get("N_THREADS", "0"))  # 0 = auto
MAX_CHARS_PER_CHUNK = int(os.environ.get("MAX_CHARS_PER_CHUNK", "45"))
API_KEY = os.environ.get("API_KEY", "changeme").strip()
REQUIRE_API_KEY = os.environ.get("REQUIRE_API_KEY", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "3430"))

PROCESS = psutil.Process()
CLI_LOCK = threading.Lock()  # qwen3-tts-cli is not designed for concurrent use

# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Qwen3-TTS Cantonese Server",
    description=(
        "CPU-only OpenAI-compatible TTS for Hong Kong Cantonese. "
        "Model: jmtl/hk-cantonese-cc0-qwen3-tts-GGUF (v0.0.5). "
        "Runtime: Danmoreng/qwen3-tts.cpp"
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def verify_api_key(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> None:
    if not REQUIRE_API_KEY:
        return
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()
    if not token or token != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Text chunking (critical for quality)
# ---------------------------------------------------------------------------

# Split on Chinese/English punctuation, keep the delimiter with previous chunk
_SPLIT_RE = re.compile(r"([，。：；！？\n]+|[.!?;:\n]+)")


def chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list[str]:
    """Split long Cantonese text into safe chunks for the model."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    parts = _SPLIT_RE.split(text)
    chunks: list[str] = []
    buf = ""

    for part in parts:
        if not part:
            continue
        # If adding this part would exceed limit, flush current buffer
        if buf and len(buf) + len(part) > max_chars:
            chunks.append(buf.strip())
            buf = ""
        buf += part
        # If buffer itself is already over limit (no punctuation), hard-split
        while len(buf) > max_chars:
            chunks.append(buf[:max_chars].strip())
            buf = buf[max_chars:]

    if buf.strip():
        chunks.append(buf.strip())

    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# Synthesis via CLI
# ---------------------------------------------------------------------------

def run_cli(
    text: str,
    output_path: Path,
    seed: int = DEFAULT_SEED,
    temperature: float = 0.9,
    top_k: int = 50,
    max_tokens: int = 4096,
) -> None:
    """Call qwen3-tts-cli. Raises RuntimeError on failure."""
    if not CLI_BIN.exists():
        raise RuntimeError(f"qwen3-tts-cli not found at {CLI_BIN}")

    talker_gguf = next(TALKER_DIR.glob("qwen-talker*.gguf"), None)
    if talker_gguf is None:
        raise RuntimeError(f"No talker GGUF found in {TALKER_DIR}")

    cmd = [
        str(CLI_BIN),
        "-m",
        str(TALKER_DIR),
        "--codec-model",
        str(CODEC_PATH),
        "--speaker",
        SPEAKER,
        "--seed",
        str(seed),
        "-t",
        text,
        "-o",
        str(output_path),
        "--temperature",
        str(temperature),
        "--top-k",
        str(top_k),
        "--max-tokens",
        str(max_tokens),
    ]
    if N_THREADS > 0:
        cmd.extend(["-j", str(N_THREADS)])

    env = os.environ.copy()
    env["QWEN3_TTS_BACKEND"] = "cpu"

    with CLI_LOCK:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"CLI failed (code {proc.returncode}): {err[:800]}")


def synthesize_to_wav_bytes(
    text: str,
    seed: int = DEFAULT_SEED,
    temperature: float = 0.9,
) -> bytes:
    """Full pipeline: chunk → synthesize each → concatenate → return WAV bytes."""
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("Empty text after cleaning")

    audio_parts: list[np.ndarray] = []
    sample_rate = 24000

    with tempfile.TemporaryDirectory(prefix="qwen3tts_") as tmpdir:
        tmp = Path(tmpdir)
        for i, chunk in enumerate(chunks):
            out_path = tmp / f"chunk_{i:03d}.wav"
            # Slightly different seed per chunk to avoid identical prosody
            chunk_seed = (seed + i * 17) % (2**31 - 1)
            run_cli(
                text=chunk,
                output_path=out_path,
                seed=chunk_seed,
                temperature=temperature,
            )
            data, sr = sf.read(out_path, dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)
            sample_rate = sr
            audio_parts.append(data)

    if not audio_parts:
        raise RuntimeError("No audio generated")

    # Small silence between chunks (~80 ms)
    silence = np.zeros(int(sample_rate * 0.08), dtype=np.float32)
    combined: list[np.ndarray] = []
    for i, part in enumerate(audio_parts):
        combined.append(part)
        if i < len(audio_parts) - 1:
            combined.append(silence)

    full = np.concatenate(combined)
    # Peak normalize lightly
    peak = np.max(np.abs(full))
    if peak > 0.99:
        full = full * (0.99 / peak)

    buf = io.BytesIO()
    sf.write(buf, full, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def wav_to_format(wav_bytes: bytes, fmt: str) -> tuple[bytes, str]:
    """Convert WAV bytes to requested response_format. Returns (data, media_type)."""
    fmt = (fmt or "wav").lower().strip()
    if fmt == "wav":
        return wav_bytes, "audio/wav"
    if fmt == "pcm":
        # raw s16le
        data, sr = sf.read(io.BytesIO(wav_bytes), dtype="int16")
        return data.tobytes(), "audio/pcm"
    if fmt in {"mp3", "mpeg"}:
        # Use ffmpeg if available
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            in_path = tmp / "in.wav"
            out_path = tmp / "out.mp3"
            in_path.write_bytes(wav_bytes)
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(in_path),
                    "-codec:a",
                    "libmp3lame",
                    "-qscale:a",
                    "2",
                    str(out_path),
                ],
                capture_output=True,
                timeout=60,
            )
            if proc.returncode != 0 or not out_path.exists():
                # Fallback to WAV
                return wav_bytes, "audio/wav"
            return out_path.read_bytes(), "audio/mpeg"
    # Unknown → WAV
    return wav_bytes, "audio/wav"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SpeechRequest(BaseModel):
    model: str = Field(default="hk-cantonese-cc0")
    input: str = Field(..., min_length=1, max_length=4096)
    voice: str = Field(default="hk_voice_343")
    response_format: str = Field(default="wav")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    # Extra
    seed: Optional[int] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, Any]:
    talker_ok = any(TALKER_DIR.glob("qwen-talker*.gguf")) if TALKER_DIR.exists() else False
    codec_ok = CODEC_PATH.exists()
    cli_ok = CLI_BIN.exists()
    ready = talker_ok and codec_ok and cli_ok
    return {
        "status": "ok" if ready else "not_ready",
        "ok": ready,
        "model": "jmtl/hk-cantonese-cc0-qwen3-tts-GGUF",
        "speaker": SPEAKER,
        "cli": str(CLI_BIN),
        "cli_exists": cli_ok,
        "talker_ready": talker_ok,
        "codec_ready": codec_ok,
        "rss_mb": round(PROCESS.memory_info().rss / 1024 / 1024, 1),
        "max_chars_per_chunk": MAX_CHARS_PER_CHUNK,
    }


@app.get("/v1/models")
def list_models(_: None = Depends(verify_api_key)) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": "hk-cantonese-cc0",
                "object": "model",
                "created": 1729814400,
                "owned_by": "jmtl",
                "root": "hk-cantonese-cc0",
            }
        ],
    }


@app.get("/v1/voices")
def list_voices(_: None = Depends(verify_api_key)) -> dict[str, Any]:
    return {
        "voices": [
            {
                "id": "hk_voice_343",
                "name": "HK Cantonese Female (CC0)",
                "language": "yue",
                "description": "Hong Kong Cantonese female voice (v0.0.5)",
            }
        ]
    }


@app.post("/v1/audio/speech")
def create_speech(
    body: SpeechRequest,
    _: None = Depends(verify_api_key),
) -> Response:
    text = body.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input must not be empty")

    # Voice is fixed for this model; accept any but always use the baked one
    seed = body.seed if body.seed is not None else DEFAULT_SEED
    temperature = body.temperature if body.temperature is not None else 0.9

    t0 = time.perf_counter()
    try:
        wav_bytes = synthesize_to_wav_bytes(
            text=text,
            seed=seed,
            temperature=temperature,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Synthesis timed out") from None

    data, media_type = wav_to_format(wav_bytes, body.response_format)
    elapsed = time.perf_counter() - t0

    # Optional speed change via ffmpeg (simple pitch-preserving time stretch is hard;
    # for now we only support speed≈1.0 cleanly; non-1.0 is best-effort)
    if abs(body.speed - 1.0) > 0.05 and body.response_format.lower() in {"wav", "mp3", "pcm"}:
        # Best-effort: use atempo (limited range 0.5-2.0)
        try:
            data = apply_atempo(data, media_type, body.speed)
        except Exception:
            pass  # keep original

    headers = {
        "X-Elapsed-Seconds": f"{elapsed:.3f}",
        "X-Chunks": str(len(chunk_text(text))),
    }
    return Response(content=data, media_type=media_type, headers=headers)


def apply_atempo(data: bytes, media_type: str, speed: float) -> bytes:
    """Best-effort speed change with ffmpeg atempo filter."""
    speed = max(0.5, min(2.0, speed))
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        in_path = tmp / "in.bin"
        out_path = tmp / "out.bin"
        in_path.write_bytes(data)

        if media_type == "audio/wav":
            cmd = [
                "ffmpeg", "-y", "-i", str(in_path),
                "-filter:a", f"atempo={speed}",
                "-f", "wav", str(out_path),
            ]
        elif media_type == "audio/mpeg":
            cmd = [
                "ffmpeg", "-y", "-i", str(in_path),
                "-filter:a", f"atempo={speed}",
                "-codec:a", "libmp3lame", "-qscale:a", "2",
                str(out_path),
            ]
        else:
            # pcm s16le 24k mono
            cmd = [
                "ffmpeg", "-y",
                "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(in_path),
                "-filter:a", f"atempo={speed}",
                "-f", "s16le", str(out_path),
            ]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode == 0 and out_path.exists():
            return out_path.read_bytes()
    return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        workers=1,
        log_level="info",
    )


if __name__ == "__main__":
    main()
