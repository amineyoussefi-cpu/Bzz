"""Decision providers: one interface, two implementations.

- OpenJevProvider asks the local OpenJev service (decision/service.py) over HTTP. It takes the decisions.
- ReferenceProvider runs the project's original choice logic in Godot (reference_decision). Comparison only.

There is no fallback from one to the other: if OpenJev is unavailable, no decision is taken.
"""

import json
import time
import urllib.error
import urllib.request

from .prompting import build_request, read_answer


class ProviderUnavailable(RuntimeError):
    """The decision service cannot be reached; no decision should be taken."""


class ProviderError(RuntimeError):
    """The service answered but could not decide this case (e.g. request too long); skip this decision."""


class DecisionProvider:
    """decide() returns {"choice": habitat id | None, "probabilities": {option: p}, "latency_ms", "model", "reason"}."""

    name = "abstract"

    def decide(self, situation: dict, candidates: list[dict]) -> dict:
        raise NotImplementedError

    def status(self) -> dict:
        raise NotImplementedError


class OpenJevProvider(DecisionProvider):
    name = "openjev"

    def __init__(self, url: str, timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.info: dict = {}  # last /health answer: model, revision, device

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        req = urllib.request.Request(self.url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code >= 500:
                raise ProviderUnavailable(f"decision service error {e.code}: {detail}") from None
            raise ProviderError(f"decision service refused the request ({e.code}): {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise ProviderUnavailable(f"decision service unreachable at {self.url}: {e}") from None

    def status(self) -> dict:
        try:
            self.info = self._call("GET", "/health", timeout=3)
        except (ProviderUnavailable, ProviderError) as e:
            return {"provider": self.name, "url": self.url, "available": False, "error": str(e)}
        return {"provider": self.name, "url": self.url, "available": True, **self.info}

    def decide(self, situation: dict, candidates: list[dict]) -> dict:
        t = time.perf_counter()
        out = self._call("POST", "/v1/systemone", build_request(situation, candidates))
        choice, probabilities, best = read_answer(out["answers"])
        accept = 1 - probabilities["none"]
        return {
            "choice": choice,
            "best": best,
            "probabilities": probabilities,
            "latency_ms": out.get("latency_ms", round((time.perf_counter() - t) * 1000)),
            "model": {k: self.info.get(k) for k in ("model", "revision", "device")},
            "reason": (f"best fit {best}, accepted (p={accept:.2f})" if choice
                       else f"best fit {best} judged below the threshold (p accept={accept:.2f})"),
        }


class ReferenceProvider(DecisionProvider):
    """The original logic (Bee.score_breakdown + choose_habitat), computed by Godot and never applied."""

    name = "reference"

    def __init__(self, engine):
        self.engine = engine

    def status(self) -> dict:
        return {"provider": self.name, "available": True}

    def decide(self, situation: dict, candidates: list[dict]) -> dict:
        ref = self.engine.send("reference_decision", bee_id=situation["bee"]["id"],
                               habitat_ids=[h["id"] for h in candidates])
        return {"choice": ref["choice"], "scores": ref["scores"], "threshold": ref["threshold"]}
