"""Bounded selection from a version-matched adopted package."""
import json
import re

from .model import Kit


def terms(value):
    return set(re.findall(r"[a-z0-9_/-]{3,}", str(value).lower()))


def is_adopted(kit):
    return kit.adoption.status == "adopted" and kit.adoption.version == kit.version


def select_context(kit: Kit, task: str, subject: str, budget=6000) -> dict:
    receipt = {"kit_id": kit.id, "version": kit.version, "subject": subject,
               "selected": [], "omitted": [], "budget": budget, "reason": ""}
    result = {"context": "", "receipt": receipt}
    if not is_adopted(kit):
        receipt["reason"] = "adoption must match current version"
        return result
    if kit.subject != subject:
        receipt["reason"] = "subject mismatch"
        return result
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ValueError("budget must be a nonnegative character count")
    task_terms = terms(task)
    selected = [step for step in kit.workflow
                if task_terms & terms(" ".join(step.keywords) if step.keywords else step.instruction)]
    if not selected:
        receipt["reason"] = "task has no declared workflow match"
        return result
    claims = {claim.id: claim for claim in kit.claims}
    sources = {source.id: source for source in kit.sources}
    choices = json.dumps({"adopted_choices": kit.adoption.choices}, ensure_ascii=False)
    blocks = [choices] if kit.adoption.choices else []
    for step in selected:
        linked = [claims[c] for c in step.claim_ids if c in claims]
        source_ids = sorted({sid for claim in linked for sid in claim.source_ids})
        payload = {"step": step.__dict__, "claims": [c.__dict__ for c in linked],
                   "sources": [{"id": sid, "url": sources[sid].url,
                                "retrieved_at": sources[sid].retrieved_at,
                                "limitations": sources[sid].limitations}
                               for sid in source_ids if sid in sources],
                   "gaps": ["missing claim " + cid for cid in step.claim_ids if cid not in claims]
                           + ["missing source " + sid for sid in source_ids if sid not in sources]}
        block = json.dumps(payload, ensure_ascii=False)
        if len("\n".join(blocks + [block])) > budget:
            receipt["omitted"].append({"id": step.id, "reason": "character budget"})
            continue
        blocks.append(block)
        receipt["selected"].append({"id": step.id, "reason": "task matches declared workflow terms",
                                    "claim_ids": step.claim_ids, "source_ids": source_ids})
    receipt["reason"] = "matched adopted workflow" if receipt["selected"] else "budget exhausted"
    result["context"] = "\n".join(blocks) if receipt["selected"] else ""
    receipt["context_chars"] = len(result["context"])
    return result
