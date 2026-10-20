"""Decision loop: while the simulation runs, every searching bee and every clustered swarm asks for a habitat
decision at a set interval (bees in flight, settled bees and exposed swarms do not).

Model calls run in worker threads (asyncio.to_thread) behind a semaphore, so they never block the API, the
WebSocket feed or other Godot commands; GodotEngine's lock keeps each Godot request/response atomic.
"""

import asyncio
import logging
import time

from ..engine import CommandRejected, GodotError
from .prompting import DEFAULT_MAX_CANDIDATES, eligible_candidates
from .providers import DecisionProvider, ProviderError, ProviderUnavailable, ReferenceProvider

log = logging.getLogger("bzz.decision")
DECIDING_STATES = ("searching", "cluster")  # bees looking for a habitat, swarms hanging on their branch


class DecisionLoop:
    def __init__(self, engine, provider: DecisionProvider, reference: DecisionProvider | None = None,
                 interval_ticks: int = 120, concurrency: int = 2, max_candidates: int = DEFAULT_MAX_CANDIDATES,
                 health_every: float = 5.0):
        self.engine = engine
        self.provider = provider
        self.reference = reference if reference is not None else ReferenceProvider(engine)
        self.interval_ticks = interval_ticks
        self.concurrency = concurrency
        self.max_candidates = max_candidates
        self.health_every = health_every
        self.pending: set[str] = set()
        self.last_round_tick: int | None = None
        self.decisions = 0
        self.last_error: str | None = None
        self.service: dict = {"provider": provider.name, "available": None}

    def status(self) -> dict:
        return {**self.service, "decisions": self.decisions, "pending": len(self.pending),
                "interval_ticks": self.interval_ticks, "concurrency": self.concurrency,
                "max_candidates": self.max_candidates, "last_error": self.last_error}

    def check_service(self) -> dict:
        self.service = self.provider.status()
        return self.service

    # --- one decision (blocking; also used by tests and the comparison script) -------------------------
    def decide_for(self, bee_id: str) -> dict | None:
        """Asks the provider for one bee, compares with the reference, applies through Godot.
        Returns the decision event data, or None when nothing was decided (paused, housed, no candidate)."""
        situation = self.engine.send("get_decision_situation", bee_id=bee_id)
        if situation["paused"] or situation["bee"]["state"] not in DECIDING_STATES:
            return None
        candidates = eligible_candidates(situation, self.max_candidates)
        if not candidates:
            return None  # nothing to choose from: no model call, no event
        decision = self.provider.decide(situation, candidates)
        reference = self.reference.decide(situation, candidates)
        data = self.event_data(situation, candidates, decision, reference)
        try:
            self.engine.send("apply_decision", bee_id=bee_id, habitat_id=decision["choice"], decision=data)
        except CommandRejected as e:
            if "paused" in str(e):
                return None  # paused while the model was thinking: dropped, not applied
            data["result"] = "rejected"  # Godot already published the rejection event
            log.info("decision for %s rejected by Godot: %s", bee_id, e)
        self.decisions += 1
        return data

    def event_data(self, situation: dict, candidates: list[dict], decision: dict, reference: dict) -> dict:
        ref_scores = {s["habitat_id"]: s for s in reference.get("scores", [])}
        bee = situation["bee"]
        context = {"distances": {h["id"]: round(h["distance"], 1) for h in candidates}}
        if bee["kind"] == "swarm":
            # the reference logic ignores both: noted in the comparison report
            context.update(population=bee["population"], days_left=round(bee["days_left"], 3))
        return {
            "context": context,
            "bee_id": situation["bee"]["id"],
            "evaluated": [{"habitat_id": h["id"], "score": decision["probabilities"].get(h["id"], 0.0),
                           "reference_score": ref_scores.get(h["id"], {}).get("score"),
                           "breakdown": ref_scores.get(h["id"], {}).get("breakdown", {})} for h in candidates],
            "chosen_habitat_id": decision["choice"],
            "reason": decision.get("reason", ""),
            "source": self.provider.name,
            "probabilities": decision["probabilities"],
            "reference": {"choice": reference.get("choice"), "threshold": reference.get("threshold")},
            "agreement": decision["choice"] == reference.get("choice"),
            "model": {**decision.get("model", {}), "latency_ms": decision.get("latency_ms")},
        }

    # --- background loop ------------------------------------------------------------------------------
    async def run(self, poll: float = 0.25) -> None:
        sem = asyncio.Semaphore(self.concurrency)
        last_health = 0.0
        while True:
            try:
                # recheck the service regularly, and sooner while it is down
                if time.monotonic() - last_health > (self.health_every if self.service.get("available") else 2.0):
                    last_health = time.monotonic()
                    await asyncio.to_thread(self.check_service)
                state = await asyncio.to_thread(self.engine.send, "get_state")
                if (not state["paused"] and self.service.get("available")
                        and (self.last_round_tick is None or state["tick"] - self.last_round_tick >= self.interval_ticks)):
                    self.last_round_tick = state["tick"]
                    entities = await asyncio.to_thread(self.engine.send, "list_entities")
                    for e in entities:
                        if e.get("state") in DECIDING_STATES and e["id"] not in self.pending:
                            self.pending.add(e["id"])
                            asyncio.create_task(self._decide(sem, e["id"]))
            except (GodotError, OSError) as e:
                self.last_error = f"godot: {e}"
            await asyncio.sleep(poll)

    async def _decide(self, sem: asyncio.Semaphore, bee_id: str) -> None:
        try:
            async with sem:
                await asyncio.to_thread(self.decide_for, bee_id)
        except ProviderUnavailable as e:
            self.service = {"provider": self.provider.name, "available": False, "error": str(e)}
            self.last_error = str(e)
        except (ProviderError, CommandRejected, GodotError, OSError) as e:
            self.last_error = str(e)
        finally:
            self.pending.discard(bee_id)
