"""Local OpenJev decision service (runs on the host, not in Docker): python decision/service.py

Serves POST /v1/systemone (OpenJev's request/response shapes) and GET /health (model, revision, device, latency).
Weights are downloaded once from Hugging Face into OPENJEV_CACHE_DIR; afterwards the model loads offline.

Environment (see .env.example):
  OPENJEV_MODEL      Hub repo (default alanhuangya/OpenJev-1.7B)
  OPENJEV_REVISION   pinned commit or tag (default: the commit validated for this project)
  OPENJEV_DEVICE     auto | cuda | mps | cpu (default auto: cuda, else mps, else cpu)
  OPENJEV_CACHE_DIR  weights cache (default decision/.cache, ignored by git)
  OPENJEV_HOST/PORT  listen address (default 127.0.0.1:8009)
"""

import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "alanhuangya/OpenJev-1.7B"
DEFAULT_REVISION = "7418ae8b6e3b6a6507a8a58729ae491cd1c732d9"  # validated on Apple M4 Pro (MPS/CPU), 2026-10-20

env = os.environ.get
MODEL = env("OPENJEV_MODEL") or DEFAULT_MODEL
REVISION = env("OPENJEV_REVISION") or DEFAULT_REVISION
DEVICE = (env("OPENJEV_DEVICE") or "auto").lower()
# must be set before huggingface_hub is imported (by wev below)
os.environ["HF_HOME"] = str((HERE / (env("OPENJEV_CACHE_DIR") or ".cache")).resolve())  # relative to decision/

import torch  # noqa: E402
import wev  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from wev.api import SystemOneRequest  # noqa: E402
from wev.model import ContextTooLong  # noqa: E402


def resolve_device(requested: str) -> str:
    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        return "mps" if torch.backends.mps.is_available() else "cpu"
    available = {"cuda": torch.cuda.is_available(), "mps": torch.backends.mps.is_available(), "cpu": True}
    if requested not in available:
        sys.exit(f"OPENJEV_DEVICE must be auto, cuda, mps or cpu (got {requested!r})")
    if not available[requested]:
        sys.exit(f"device {requested!r} is not available on this machine")
    return requested


def load_model(device: str):
    """Offline from the cache when the pinned revision is there; online (first run only) otherwise."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        return wev.load(MODEL, device=device, revision=REVISION)
    except Exception:  # not cached yet
        os.environ["HF_HUB_OFFLINE"] = "0"
        print(f"downloading {MODEL}@{REVISION[:12]} into {os.environ['HF_HOME']} (first run only)...", flush=True)
        model = wev.load(MODEL, device=device, revision=REVISION)
        os.environ["HF_HUB_OFFLINE"] = "1"
        return model


app = FastAPI(title="Bzz decision service (OpenJev)")
S = {"model": None, "device": None, "latencies": [], "requests": 0, "errors": 0}
_lock = threading.Lock()  # one forward pass at a time: the model is not shared across threads safely


@app.get("/health")
def health():
    lat = S["latencies"][-100:]
    return {"status": "ok", "model": MODEL, "revision": REVISION, "device": S["device"],
            "dtype": str(next(S["model"].model.parameters()).dtype).removeprefix("torch."),
            "requests": S["requests"], "errors": S["errors"],
            "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else None}


@app.post("/v1/systemone")
def systemone(req: SystemOneRequest):
    t = time.perf_counter()
    try:
        with _lock:
            out = S["model"].predict_request(req)
    except ContextTooLong as e:
        S["errors"] += 1
        raise HTTPException(422, f"request too long: {e}") from None
    S["requests"] += 1
    S["latencies"].append((time.perf_counter() - t) * 1000)
    del S["latencies"][:-1000]
    return out


def main() -> None:
    import uvicorn

    S["device"] = resolve_device(DEVICE)
    t = time.perf_counter()
    S["model"] = load_model(S["device"])
    print(f"OpenJev ready: model={MODEL} revision={REVISION[:12]} device={S['device']} "
          f"(requested {DEVICE}) loaded in {time.perf_counter() - t:.1f}s", flush=True)
    uvicorn.run(app, host=env("OPENJEV_HOST") or "127.0.0.1", port=int(env("OPENJEV_PORT") or 8009))


if __name__ == "__main__":
    main()
