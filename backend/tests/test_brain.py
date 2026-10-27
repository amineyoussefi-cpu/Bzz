"""Unit tests of the bee brain with a fake LLM (no Ollama needed). Run: python -m unittest discover backend/tests"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bzz.brain import NOTEBOOK_SIZE, Brain, personality_card

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

    def test_notebook_keeps_only_last_lines(self):
        brain = Brain(FakeLLM(*[{"choice": "go_back"}] * (NOTEBOOK_SIZE + 2)))
        for _ in range(NOTEBOOK_SIZE + 2):
            brain.decide(BEE, "stay_or_leave", {"habitat": SITE})
        self.assertEqual(len(brain.notebooks["bee-1"]), NOTEBOOK_SIZE)


if __name__ == "__main__":
    unittest.main()
