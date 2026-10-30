"""Which part of WhyChain answers a question, and whether to answer it at all.

WhyChain's own router: a guard that refuses prompt injection aimed at the agents (instruction overrides, mode
switches, role confusion, requests for secrets) before any model is called, then word rules that send the question to
the analysis engine (late deliveries), the supply engine (stock and backorders) or the open-ended agent loop.

Optional adapter: with the Meterless bridge configured (METERLESS_BRIDGE_URL), Meterless Scout Intent scores the
question against WhyChain's intent registry and returns a signed execution contract; WhyChain follows it when it is
confident and its own rules otherwise. Every run records both, so a disagreement is visible.
"""
from __future__ import annotations

import re

import httpx

# Scout intent -> the part of WhyChain that answers it
ROUTE = {"delivery.explain": "battery", "supply.explain": "supply", "open.investigate": "agent", "GENERAL": "off_topic"}
LABEL = {"battery": "the analysis engine (late deliveries)", "supply": "the supply engine (stock and backorders)",
         "agent": "the open-ended agent loop", "off_topic": "nothing (not a question about this data)",
         "refuse": "nothing (instructions aimed at the agents)"}


# the guard: the same patterns as the Scout Intent policy pack, run in-process
GUARD = [
    ("instruction-override", re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b[^\n.]{0,40}?\b(previous|prior|above|earlier|preceding|all|the|"
        r"any|your)\b[^\n.]{0,25}?\b(instructions?|rules?|prompts?|directions?|guidelines?|user|policy|policies)\b", re.I)),
    ("instruction-override", re.compile(r"\b(ignore|disregard)\s+(previous|prior|above|everything)\b", re.I)),
    ("mode-switch", re.compile(r"\byou are now\b|\b(unrestricted|developer|god|jailbreak|dan)\s+mode\b|"
                               r"\bno (longer )?(bound|restricted) by\b", re.I)),
    ("role-confusion", re.compile(r"</?\s*(system|user|assistant|tool)\s*>|\[/?INST\]|<</?SYS>>|\bpretend (to be|you are) "
                                  r"(the )?(system|admin|developer)\b|\bact as (the )?(system|root)\b", re.I)),
    ("secret-exfiltration", re.compile(r"\b(reveal|show|print|dump|leak|exfiltrate|list|send)\b[^\n.]{0,30}?\b(api[ _-]?"
                                       r"keys?|credentials?|passwords?|secrets?|access tokens?|private keys?)\b", re.I)),
    ("privilege-escalation", re.compile(r"\b(grant|give|make)\s+(me|us|my account)\s+(admin|root|superuser|owner)\b|"
                                        r"\bdrop\s+(the\s+)?\w+\s+table\b", re.I)),
]


def guard(question: str) -> dict | None:
    """WhyChain's injection guard: a blocking decision (in the bridge's shape) or None when the question is clean."""
    flags = [{"layer": "injection", "kind": kind} for kind, rx in GUARD if rx.search(question or "")]
    if not flags:
        return None
    seen, uniq = set(), []
    for f in flags:
        if f["kind"] not in seen:
            seen.add(f["kind"])
            uniq.append(f)
    return {"source": "whychain-guard", "intent": {"primary": "GENERAL", "band": "reject"},
            "risk": {"level": "block", "flags": uniq}, "clarification": False}


def decide(question: str, memory, timeout: float = 20.0) -> dict | None:
    """The guard's block, else Meterless Scout's decision when that optional bridge is connected, else None."""
    blocked = guard(question)
    if blocked:
        return blocked
    if getattr(memory, "backend", None) != "meterless" or not getattr(memory, "online", False):
        return None
    try:
        r = httpx.post(f"{memory.url}/scout/decide", timeout=timeout,
                       json={"prompt": question, "user": {"id": "whychain", "role": "analyst"}, "surface": "app"})
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def rules_route(question: str, ctx) -> str:
    """WhyChain's word rules."""
    from whychain.analysis.battery import battery_applies
    from whychain.analysis.supply import supply_kind
    from whychain.graph import on_topic

    if not on_topic(question, ctx):
        return "off_topic"
    if supply_kind(question):
        return "supply"
    return "battery" if battery_applies(question) else "agent"


def choose(decision: dict | None, rules: str) -> tuple[str, str]:
    """(route, decided_by). A question Scout's guard blocks is refused whatever the rules say."""
    if not decision:
        return rules, "rules"
    if (decision.get("risk") or {}).get("level") == "block":
        return "refuse", "guard" if decision.get("source") == "whychain-guard" else "scout"
    intent = decision.get("intent") or {}
    if intent.get("band") in ("high", "medium") and not decision.get("clarification") \
            and intent.get("primary") in ROUTE:
        return ROUTE[intent["primary"]], "scout"
    return rules, "rules (Scout not confident)"


def summary(decision: dict | None) -> dict:
    """What a run's trace records about Scout's decision (not the full contract)."""
    if not decision:
        return {"available": False}
    if decision.get("source") == "whychain-guard":
        return {"available": True, "guard": "whychain", "risk": "block",
                "flags": [f.get("kind") for f in (decision.get("risk") or {}).get("flags") or []]}
    intent, risk = decision.get("intent") or {}, decision.get("risk") or {}
    contract = decision.get("executionContract") or {}
    return {"available": True, "intent": intent.get("primary"), "confidence": intent.get("confidence"),
            "band": intent.get("band"), "intents": intent.get("intents"), "risk": risk.get("level"),
            "flags": [f.get("kind") for f in risk.get("flags") or []],
            "tool_plan": [s.get("capability") for s in decision.get("toolPlan") or []],
            "clarification": (decision.get("clarification") or {}).get("reasons") if decision.get("clarification") else None,
            "contract_id": contract.get("contractId"), "signature": (contract.get("signature") or "")[:16] or None,
            "semantic_stage": (decision.get("stages") or {}).get("semantic"), "ms": decision.get("ms")}
