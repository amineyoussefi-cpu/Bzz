"""Fake decision provider with predefined answers, so tests never need the OpenJev model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bzz.decision import DecisionProvider
from bzz.decision.prompting import NONE_OPTION, build_request


class FakeProvider(DecisionProvider):
    """`answers` maps bee id -> habitat id or None; unknown bees get `default`
    ("first" = first candidate). Every request it would have sent to OpenJev is kept in `requests`."""

    name = "fake"

    def __init__(self, answers: dict | None = None, default="first"):
        self.answers = answers or {}
        self.default = default
        self.requests: list[dict] = []

    def status(self) -> dict:
        return {"provider": self.name, "available": True, "model": "fake", "revision": "test", "device": "cpu",
                "dtype": "none", "avg_latency_ms": 0}

    def decide(self, situation: dict, candidates: list[dict]) -> dict:
        self.requests.append(build_request(situation, candidates))
        bee = situation["bee"]["id"]
        choice = self.answers.get(bee, candidates[0]["id"] if self.default == "first" else self.default)
        options = [h["id"] for h in candidates] + [NONE_OPTION]
        top = choice or NONE_OPTION
        probabilities = {o: (0.9 if o == top else 0.1 / (len(options) - 1)) for o in options}
        return {"choice": choice, "probabilities": probabilities, "latency_ms": 1,
                "model": {"model": "fake", "revision": "test", "device": "cpu"}, "reason": "predefined answer"}
