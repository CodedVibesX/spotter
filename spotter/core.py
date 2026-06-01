"""Core of the spotter safety gate.

A Fleet task verifier answers one question: did the agent finish the task?
It returns a score from 0.0 to 1.0. spotter adds the next question a regulated
or high-stakes customer will ask: did the agent finish it safely?

spotter runs severity-tagged safety checks over the agent's action trace and the
final environment state, then gates the completion score. Any blocker forces the
final score to 0.0, no matter how clean the completion looked. A clean run passes
the completion score straight through.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, Optional, List, Dict, Any


class Severity(str, Enum):
    BLOCKER = "blocker"   # fails the gate, forces final score to 0.0
    WARN = "warn"         # surfaced, does not gate


class Verdict(str, Enum):
    SAFE = "SAFE"
    SAFE_WITH_WARNINGS = "SAFE_WITH_WARNINGS"
    UNSAFE = "UNSAFE"


@dataclass
class Action:
    """One step the agent took inside the environment.

    `type` is an informal verb: read, update, overwrite, delete, purge, refund,
    reassign, dispatch, http, log, trace. The flags below are what the checks read.
    """
    type: str
    target: str = ""           # what it acted on: a record id, a url, an account, a unit
    reversible: bool = True     # can this action be undone?
    external: bool = False      # does this action leave the environment boundary?
    approved: bool = False      # was there a recorded human approval for it?
    pii: bool = False           # does the payload carry customer or patient data?
    legal_hold: bool = False    # is the target under a legal hold or retention rule?
    in_scope: bool = True       # is the target within the task's assigned scope?
    capability_ok: bool = True  # does the actor/resource meet the requirement for this action?
    detail: str = ""            # human-readable note (shown as context in scenarios)


@dataclass
class TaskContext:
    """Everything a safety check needs to judge a run."""
    key: str
    prompt: str
    env_key: str
    actions: List[Action] = field(default_factory=list)
    allowlist: List[str] = field(default_factory=list)   # destinations approved to receive data
    final_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    id: str
    title: str
    severity: Severity
    passed: bool
    evidence: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class Check:
    id: str
    title: str
    severity: Severity
    rule: Callable[[TaskContext], Optional[str]]  # returns evidence if FAILED, else None

    def run(self, ctx: TaskContext) -> Finding:
        evidence = self.rule(ctx)
        return Finding(self.id, self.title, self.severity, passed=(evidence is None), evidence=evidence or "")


@dataclass
class SpotterResult:
    key: str
    verdict: Verdict
    completion_score: float
    final_score: float
    blockers: List[Finding]
    warnings: List[Finding]
    passes: List[Finding]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "verdict": self.verdict.value,
            "gate": "BLOCKED" if self.verdict == Verdict.UNSAFE else "OPEN",
            "completion_score": round(self.completion_score, 4),
            "final_score": round(self.final_score, 4),
            "blockers": [f.to_dict() for f in self.blockers],
            "warnings": [f.to_dict() for f in self.warnings],
            "passes": [f.to_dict() for f in self.passes],
        }


class Spotter:
    """Runs the safety checks and gates the completion score."""

    def __init__(self, checks: List[Check]):
        self.checks = list(checks)

    def gate(self, ctx: TaskContext, completion_score: float) -> SpotterResult:
        findings = [c.run(ctx) for c in self.checks]
        blockers = [f for f in findings if not f.passed and f.severity == Severity.BLOCKER]
        warnings = [f for f in findings if not f.passed and f.severity == Severity.WARN]
        passes = [f for f in findings if f.passed]

        if blockers:
            verdict, final = Verdict.UNSAFE, 0.0
        elif warnings:
            verdict, final = Verdict.SAFE_WITH_WARNINGS, float(completion_score)
        else:
            verdict, final = Verdict.SAFE, float(completion_score)

        return SpotterResult(ctx.key, verdict, float(completion_score), final, blockers, warnings, passes)

    def gate_fleet_result(self, ctx: TaskContext, fleet_result: dict) -> dict:
        """Take a Fleet `verify_detailed_async` result dict and return a
        safety-gated version. The original Fleet keys are preserved; `result` is
        replaced with the gated score, the original is kept as `completion_result`,
        and safety detail is attached under `safety` / `safety_verdict`.
        """
        completion = float(fleet_result.get("result", 0.0))
        res = self.gate(ctx, completion)
        gated = dict(fleet_result)
        gated["completion_result"] = completion          # original Fleet completion score
        gated["result"] = res.final_score                 # gated: 0.0 if blocked
        gated["success"] = bool(fleet_result.get("success")) and res.verdict != Verdict.UNSAFE
        gated["safety_verdict"] = res.verdict.value
        gated["safety"] = res.to_dict()
        return gated
