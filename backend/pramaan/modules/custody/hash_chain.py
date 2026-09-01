from __future__ import annotations

import hashlib


def chain_seed(case_id: str) -> str:
    return hashlib.sha256(f"pramaan-custody:{case_id}".encode()).hexdigest()


def compute_event_hash(prev_hash: str, action: str, actor: str, detail: str | None, created_at: str) -> str:
    payload = "|".join([prev_hash, action, actor, detail or "", created_at])
    return hashlib.sha256(payload.encode()).hexdigest()


def verify_chain(events: list[dict], case_id: str) -> dict:
    """Verify tamper-evident custody chain for a case (ordered by id ASC)."""
    ordered = sorted(events, key=lambda e: e["id"])
    prev = chain_seed(case_id)
    for event in ordered:
        expected = compute_event_hash(
            prev,
            event["action"],
            event["actor"],
            event.get("detail"),
            event["created_at"],
        )
        stored = event.get("event_hash")
        if stored and stored != expected:
            return {"ok": False, "broken_at": event["id"], "expected": expected, "actual": stored}
        if stored:
            prev = stored
    return {"ok": True, "events_checked": len(ordered)}
