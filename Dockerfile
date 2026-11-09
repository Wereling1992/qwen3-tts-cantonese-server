# =============================================================================
# Stage 1: Build qwen3-tts.cpp (CPU-only)
# =============================================================================
FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ca-certificates \
    pkg-config \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Use the commit recommended by the Cantonese model card
ARG QWEN3_TTS_CPP_REPO=https://github.com/Danmoreng/qwen3-tts.cpp.git
ARG QWEN3_TTS_CPP_REF=16bb5afcd06311031c72a8488f8d59660dc2fb46

# Full clone of the pinned commit + submodules
RUN git clone "${QWEN3_TTS_CPP_REPO}" qwen3-tts.cpp \
    && cd qwen3-tts.cpp \
    && git checkout "${QWEN3_TTS_CPP_REF}" \
    && git submodule update --init --recursive \
    && test -f ggml/CMakeLists.txt \
    && test -f ggml/include/ggml.h

WORKDIR /src/qwen3-tts.cpp

# CPU-only build with arch-specific flags.
# ARM64 needs +fp16 or the NEON fp16 intrinsics fail to inline.
# x86_64 keeps a portable baseline (no -march=native).
RUN set -eux; \
    ARCH="$(uname -m)"; \
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
      EXTRA_FLAGS="-march=armv8.2-a+fp16 -Wno-pedantic"; \
    else \
      EXTRA_FLAGS="-O3 -Wno-pedantic"; \
    fi; \
    cmake -S . -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_CUDA=OFF \
        -DQWEN3_TTS_CUDA=OFF \
        -DQWEN3_TTS_EMBED_GGML=ON \
        -DGGML_NATIVE=OFF \
        -DBUILD_SHARED_LIBS=ON \
        -DCMAKE_CXX_FLAGS="${EXTRA_FLAGS}" \
        -DCMAKE_CXX_FLAGS_RELEASE="-O3 ${EXTRA_FLAGS}" \
        -DCMAKE_C_FLAGS="${EXTRA_FLAGS}" \
        -DCMAKE_C_FLAGS_RELEASE="-O3 ${EXTRA_FLAGS}" \
    && cmake --build build -j"$(nproc)" \
    && test -x build/qwen3-tts-cli \
    && mkdir -p /opt/qwen3-tts/bin /opt/qwen3-tts/lib \
    && cp -a build/qwen3-tts-cli /opt/qwen3-tts/bin/ \
    && find build -type f \( -name 'libggml*.so*' -o -name 'libggml*.dylib' \) -exec cp -a {} /opt/qwen3-tts/lib/ \; \
    && ls -la /opt/qwen3-tts/bin/ /opt/qwen3-tts/lib/

# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libsndfile1 \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# CLI + ggml shared libraries
COPY --from=builder /opt/qwen3-tts/bin/qwen3-tts-cli /usr/local/bin/qwen3-tts-cli
COPY --from=builder /opt/qwen3-tts/lib/ /usr/local/lib/
RUN chmod +x /usr/local/bin/qwen3-tts-cli \
    && ldconfig \
    && qwen3-tts-cli --help >/dev/null 2>&1 || true

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY server.py .
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Non-sensitive defaults only.
# Pass secrets at runtime, e.g.  -e API_KEY=your-secret
ENV MODELS_DIR=/models \
    QWEN3_TTS_CLI=/usr/local/bin/qwen3-tts-cli \
    SPEAKER=hk_voice_343 \
    DEFAULT_SEED=20260905 \
    N_THREADS=0 \
    MAX_CHARS_PER_CHUNK=45 \
    HOST=0.0.0.0 \
    PORT=3430 \
    HF_HUB_ENABLE_HF_TRANSFER=0 \
    LD_LIBRARY_PATH=/usr/local/lib

EXPOSE 3430

HEALTHCHECK --interval=30s --timeout=15s --start-period=300s --retries=5 \
    CMD curl -f http://localhost:3430/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "server.py"]
