"""Unit tests of the bee brain with a fake LLM (no Ollama needed). Run: python -m unittest discover backend/tests"""

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bzz.brain import NOTEBOOK_SIZE, Brain, OllamaLLM, personality_card

BEE = {"id": "bee-1", "personality": {"pickiness": 0.8, "boldness": 0.1, "sociability": 0.4, "curiosity": 0.2}}
SITE = {"id": "hab-A", "description": {"cavity_volume_l": "large cavity", "predator_risk": "safe"}}
DANCES = [{"site_id": "hab-A", "strength": "strongly", "direction": "north"},
          {"site_id": "hab-B", "strength": "weakly", "direction": "east"}]


class FakeLLM:
    """Returns the queued answers in order and records every call."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, messages, schema, seed):
        self.calls.append({"messages": messages, "schema": schema, "seed": seed})
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a if isinstance(a, str) else json.dumps(a)


class BrainTest(unittest.TestCase):
    def test_personality_in_words(self):
        self.assertEqual(personality_card(BEE["personality"]), "very picky, not at all bold, moderately sociable, slightly curious")

    def test_one_call_per_decision_with_card_situation_and_notebook(self):
        llm = FakeLLM({"score": 5}, {"choice": "stay"})
        brain = Brain(llm)
        self.assertEqual(brain.decide(BEE, "evaluate_site", {"habitat": SITE}), {"score": 5})
        self.assertEqual(brain.decide(BEE, "stay_or_leave", {"habitat": SITE}), {"choice": "stay"})
        self.assertEqual(len(llm.calls), 2)
        system, user = llm.calls[1]["messages"]
        self.assertIn("very picky", system["content"])
        self.assertIn("large cavity, safe", user["content"])
        self.assertIn("scored it 5/5", user["content"])  # the notebook carries the first decision into the second
        self.assertEqual(list(brain.notebooks["bee-1"])[-1], "stayed at site hab-A")

    def test_seed_reproducible_per_bee_and_different_between_bees(self):
        self.assertEqual(Brain(FakeLLM(), run_seed=7).seed("bee-1"), Brain(FakeLLM(), run_seed=7).seed("bee-1"))
        self.assertNotEqual(Brain(FakeLLM(), run_seed=7).seed("bee-1"), Brain(FakeLLM(), run_seed=7).seed("bee-2"))
        self.assertNotEqual(Brain(FakeLLM(), run_seed=7).seed("bee-1"), Brain(FakeLLM(), run_seed=8).seed("bee-1"))

    def test_invalid_answer_retried_with_another_seed(self):
        llm = FakeLLM("not json", {"follow": "hab-B"})
        brain = Brain(llm)
        self.assertEqual(brain.decide(BEE, "judge_dances", {"dances": DANCES}), {"follow": "hab-B"})
        self.assertEqual(llm.calls[1]["seed"], llm.calls[0]["seed"] + 1)
        self.assertEqual(brain.failures, 0)

    def test_two_bad_answers_fall_back_to_default_and_count(self):
        cases = [("evaluate_site", {"habitat": SITE}, {"score": 9}, {"score": 1}),
                 ("judge_dances", {"dances": DANCES}, {"follow": "hab-Z"}, {"follow": "none"}),  # site nobody danced for
                 ("stay_or_leave", {"habitat": SITE}, {"choice": "fly away"}, {"choice": "go_back"})]
        brain = Brain(FakeLLM(*[bad for _, _, bad, _ in cases for _ in range(2)]))
        for kind, situation, _, default in cases:
            self.assertEqual(brain.decide(BEE, kind, situation), default)
        self.assertEqual(brain.failures, 3)

    def test_unreachable_llm_falls_back(self):
        brain = Brain(FakeLLM(OSError("connection refused"), OSError("connection refused")))
        self.assertEqual(brain.decide(BEE, "stay_or_leave", {"habitat": SITE}), {"choice": "go_back"})
        self.assertEqual(brain.failures, 1)

    def test_each_call_is_logged_with_prompt_and_raw_replies(self):
        brain = Brain(FakeLLM("oops", {"score": 4}))
        brain.decide(BEE, "evaluate_site", {"habitat": SITE}, tick=120)
        call = brain.calls["bee-1"][-1]
        self.assertEqual((call["tick"], call["kind"], call["answer"], call["fallback"]), (120, "evaluate_site", {"score": 4}, False))
        self.assertEqual([a["raw"] for a in call["attempts"]], ["oops", '{"score": 4}'])
        self.assertIn("large cavity", call["messages"][1]["content"])
        brain = Brain(FakeLLM(OSError("refused"), OSError("refused")))
        brain.decide(BEE, "stay_or_leave", {"habitat": SITE})
        self.assertTrue(brain.calls["bee-1"][-1]["fallback"])
        self.assertIn("refused", brain.calls["bee-1"][-1]["attempts"][0]["error"])

    def test_notebook_keeps_only_last_lines(self):
        brain = Brain(FakeLLM(*[{"choice": "go_back"}] * (NOTEBOOK_SIZE + 2)))
        for _ in range(NOTEBOOK_SIZE + 2):
            brain.decide(BEE, "stay_or_leave", {"habitat": SITE})
        self.assertEqual(len(brain.notebooks["bee-1"]), NOTEBOOK_SIZE)


class FakeOllama(BaseHTTPRequestHandler):
    """Minimal stand-in for Ollama's /api/tags, /api/pull and /api/chat; records request bodies."""

    requests: list = []

    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply(200, {"models": [{"name": "qwen2.5:0.5b", "size": 397_000_000, "digest": "x"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append((self.path, body))
        if self.path == "/api/pull":
            self._reply(200, {"status": "success"} if body["model"] == "qwen2.5:0.5b" else {"error": "file does not exist"})
        else:
            self._reply(200, {"message": {"role": "assistant", "content": '{"score": 3}'}})

    def log_message(self, *args):
        pass


class OllamaLLMTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.llm = OllamaLLM(url=f"http://127.0.0.1:{cls.server.server_port}/", model="qwen2.5:0.5b")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_installed_models(self):
        self.assertEqual(self.llm.installed(), [{"name": "qwen2.5:0.5b", "size": 397_000_000}])

    def test_chat_sends_model_schema_temperature_and_seed(self):
        self.assertEqual(self.llm([{"role": "user", "content": "hi"}], {"type": "object"}, 42), '{"score": 3}')
        path, body = FakeOllama.requests[-1]
        self.assertEqual(path, "/api/chat")
        self.assertEqual((body["model"], body["format"], body["stream"]), ("qwen2.5:0.5b", {"type": "object"}, False))
        self.assertEqual(body["options"], {"temperature": 0.7, "seed": 42})

    def test_pull(self):
        self.llm.pull("qwen2.5:0.5b")
        self.assertEqual(FakeOllama.requests[-1], ("/api/pull", {"model": "qwen2.5:0.5b", "stream": False}))
        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.llm.pull("nope:1b")

    def test_unreachable_raises_oserror(self):
        with self.assertRaises(OSError):
            OllamaLLM(url="http://127.0.0.1:9", timeout=2).installed()


if __name__ == "__main__":
    unittest.main()
