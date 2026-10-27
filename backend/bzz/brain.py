"""Bee brain: one LLM call ("intelligence token") per decision, plus a small notebook per bee kept here.

The LLM keeps no memory between calls. Each prompt is rebuilt from the bee's personality card, its notebook
and the current situation (habitat words from Godot's `describe()`, dances seen). See docs/methode_jeton.md.

Bees and habitats are the dicts Godot's get_entity returns ({"id", "personality", ...} / {"id", "description"}).

Configured by environment variables:
  OLLAMA_URL   Ollama server (default http://localhost:11434)
  BZZ_MODEL    model name (default qwen2.5:0.5b)
"""

import json
import os
import urllib.request
import zlib
from collections import defaultdict, deque

TEMPERATURE = 0.7
NOTEBOOK_SIZE = 5  # lines kept per bee; small models get lost in long prompts

# Personality traits (0..1) in words, on the same 5 levels as the habitat features.
_TRAIT_WORDS = {"pickiness": "picky", "boldness": "bold", "sociability": "sociable", "curiosity": "curious"}
_DEGREES = ["not at all", "slightly", "moderately", "quite", "very"]


def personality_card(personality: dict) -> str:
    return ", ".join(f"{_DEGREES[min(int(personality[t] * 5), 4)]} {w}" for t, w in _TRAIT_WORDS.items())


def site_words(habitat: dict) -> str:
    return ", ".join(habitat["description"].values())


def _evaluate_site(s):
    return (f"You are inspecting site {s['habitat']['id']}: {site_words(s['habitat'])}.\n"
            "How good is it as a home for your swarm? Answer with a score from 1 (terrible) to 5 (perfect).")


def _judge_dances(s):
    seen = "\n".join(f"- a bee dances {d['strength']} for site {d['site_id']}, {d['direction']}" for d in s["dances"])
    return f"On the swarm you see these dances:\n{seen}\nDo you go and inspect one site yourself? Answer its id, or \"none\"."


def _stay_or_leave(s):
    return (f"You are at site {s['habitat']['id']}: {site_words(s['habitat'])}.\n"
            "Do you stay here or go back to the swarm? Answer \"stay\" or \"go_back\".")


# Each decision: question, answer schema (sent to the LLM), check of the answer, default answer, notebook line.
DECISIONS = {
    "evaluate_site": {
        "question": _evaluate_site,
        "schema": {"type": "object", "properties": {"score": {"type": "integer", "minimum": 1, "maximum": 5}},
                   "required": ["score"]},
        "valid": lambda a, s: type(a.get("score")) is int and 1 <= a["score"] <= 5,
        "default": lambda s: {"score": 1},
        "note": lambda a, s: f"inspected site {s['habitat']['id']} ({site_words(s['habitat'])}): scored it {a['score']}/5",
    },
    "judge_dances": {
        "question": _judge_dances,
        "schema": {"type": "object", "properties": {"follow": {"type": "string"}}, "required": ["follow"]},
        "valid": lambda a, s: a.get("follow") in ["none"] + [d["site_id"] for d in s["dances"]],
        "default": lambda s: {"follow": "none"},
        "note": lambda a, s: "ignored the dances" if a["follow"] == "none" else f"followed a dance to site {a['follow']}",
    },
    "stay_or_leave": {
        "question": _stay_or_leave,
        "schema": {"type": "object", "properties": {"choice": {"type": "string", "enum": ["stay", "go_back"]}},
                   "required": ["choice"]},
        "valid": lambda a, s: a.get("choice") in ("stay", "go_back"),
        "default": lambda s: {"choice": "go_back"},
        "note": lambda a, s: ("stayed at" if a["choice"] == "stay" else "left") + f" site {s['habitat']['id']}",
    },
}


class OllamaLLM:
    """Calls a local Ollama server. `__call__` returns the raw text of the answer."""

    def __init__(self, url: str | None = None, model: str | None = None, timeout: float = 60):
        self.url = (url or os.environ.get("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
        self.model = model or os.environ.get("BZZ_MODEL") or "qwen2.5:0.5b"
        self.timeout = timeout

    def __call__(self, messages: list, schema: dict, seed: int) -> str:
        body = {"model": self.model, "messages": messages, "format": schema, "stream": False,
                "options": {"temperature": TEMPERATURE, "seed": seed}}
        req = urllib.request.Request(f"{self.url}/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)["message"]["content"]


class Brain:
    """Turns a decision request into one LLM call and keeps each bee's notebook."""

    def __init__(self, llm=None, run_seed: int = 0):
        self.llm = llm or OllamaLLM()
        self.run_seed = run_seed
        self.notebooks: dict[str, deque] = defaultdict(lambda: deque(maxlen=NOTEBOOK_SIZE))
        self.failures = 0  # decisions that fell back to the default answer (a measure in itself for small models)

    def seed(self, bee_id: str) -> int:
        # Same run + same bee -> same seed (reproducible); different bees -> different seeds (variety).
        return zlib.crc32(f"{self.run_seed}:{bee_id}".encode())

    def prompt(self, bee: dict, kind: str, situation: dict) -> list:
        notebook = "\n".join(f"- {line}" for line in self.notebooks[bee["id"]]) or "- nothing yet"
        system = (f"You are a honey bee looking for a new home with your swarm. "
                  f"Your personality: {personality_card(bee['personality'])}. Answer only in JSON.")
        user = f"Your notebook:\n{notebook}\n\n{DECISIONS[kind]['question'](situation)}"
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def decide(self, bee: dict, kind: str, situation: dict) -> dict:
        """One intelligence token: asks the LLM (one retry), falls back to the default, notes the outcome."""
        d = DECISIONS[kind]
        messages = self.prompt(bee, kind, situation)
        answer = None
        for attempt in range(2):
            try:  # the retry shifts the seed, else the same prompt gives the same bad answer again
                candidate = json.loads(self.llm(messages, d["schema"], self.seed(bee["id"]) + attempt))
            except (ValueError, OSError):  # bad JSON, or Ollama unreachable / timed out
                continue
            if isinstance(candidate, dict) and d["valid"](candidate, situation):
                answer = candidate
                break
        if answer is None:
            self.failures += 1
            answer = d["default"](situation)
        self.notebooks[bee["id"]].append(d["note"](answer, situation))
        return answer
