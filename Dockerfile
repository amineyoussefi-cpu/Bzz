# Multi-target build:  --target godot   -> headless Godot simulation server
#                      --target backend -> Python backend (also ships Godot, so it can spawn one or run the tests)

ARG GODOT_VERSION=4.7.2

FROM debian:bookworm-slim AS godot-bin
ARG GODOT_VERSION
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*
RUN case "$TARGETARCH" in \
        amd64) arch=x86_64 ;; \
        arm64) arch=arm64 ;; \
        *) echo "unsupported arch: $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /tmp/godot.zip \
        "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable/Godot_v${GODOT_VERSION}-stable_linux.${arch}.zip" \
    && unzip -q /tmp/godot.zip -d /tmp/godot \
    && mv /tmp/godot/Godot_v${GODOT_VERSION}-stable_linux.${arch} /usr/local/bin/godot \
    && chmod +x /usr/local/bin/godot


FROM debian:bookworm-slim AS godot
RUN apt-get update && apt-get install -y --no-install-recommends libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=godot-bin /usr/local/bin/godot /usr/local/bin/godot
WORKDIR /app/godot
COPY godot/ ./
# pre-build the .godot import cache so startup doesn't do it
RUN godot --headless --import --path . || true
ENV GODOT_PORT=9876
EXPOSE 9876
CMD ["sh", "-c", "exec godot --headless --path . -- --host=0.0.0.0 --port=${GODOT_PORT}"]


FROM python:3.12-slim AS backend
RUN apt-get update && apt-get install -y --no-install-recommends libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=godot-bin /usr/local/bin/godot /usr/local/bin/godot
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY godot/ godot/
COPY backend/ backend/
WORKDIR /app/backend
CMD ["python", "-m", "bzz"]
