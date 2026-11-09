#!/bin/bash
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-/models}"
TALKER_DIR="${MODELS_DIR}/talker"
CODEC_FILE="${MODELS_DIR}/qwen-tokenizer-12hz-q8_0.gguf"
REPO_ID="jmtl/hk-cantonese-cc0-qwen3-tts-GGUF"

mkdir -p "${TALKER_DIR}"

need_download=0
if ! ls "${TALKER_DIR}"/qwen-talker*.gguf 1>/dev/null 2>&1; then
  need_download=1
fi
if [ ! -f "${CODEC_FILE}" ]; then
  need_download=1
fi

if [ "${need_download}" = "1" ]; then
  echo ">>> Models not found. Downloading from Hugging Face: ${REPO_ID}"
  echo ">>> This is ~2.3 GB and may take several minutes on first start."
  if [ -n "${HF_TOKEN:-}" ] || [ -n "${HUGGING_FACE_HUB_TOKEN:-}" ]; then
    echo ">>> Using authenticated Hugging Face token (higher rate limits)."
  else
    echo ">>> Tip: set HF_TOKEN to avoid rate limits and speed up downloads."
  fi
  python - <<'PY'
import os
import sys
from pathlib import Path
from huggingface_hub import hf_hub_download

repo_id = "jmtl/hk-cantonese-cc0-qwen3-tts-GGUF"
models_dir = Path(os.environ.get("MODELS_DIR", "/models"))
talker_dir = models_dir / "talker"
talker_dir.mkdir(parents=True, exist_ok=True)

# Optional auth (HF_TOKEN or HUGGING_FACE_HUB_TOKEN)
token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or None

def dl(filename: str, local_dir: Path) -> str:
    print(f"Downloading {filename} ...", flush=True)
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(local_dir),
        token=token,
    )
    print(f"  -> {path}", flush=True)
    return path

try:
    dl("qwen-talker-hk-cantonese-cc0-v0.0.5-q8_0.gguf", talker_dir)
    dl("qwen-tokenizer-12hz-q8_0.gguf", models_dir)
except Exception as e:
    print(f"ERROR: model download failed: {e}", file=sys.stderr, flush=True)
    sys.exit(1)

print("Download complete.", flush=True)
PY
else
  echo ">>> Models already present under ${MODELS_DIR}"
fi

echo ">>> Starting server on ${HOST:-0.0.0.0}:${PORT:-3430}"
exec "$@"
