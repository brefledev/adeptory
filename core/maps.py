"""Portable professional meanings and capability gaps."""
from .model import Kit


def map_errors(entries: list, source_ids: set, workflow_ids: set) -> list[str]:
    errors = []
    seen = set()
    for index, entry in enumerate(entries):
        prefix = f"data_map[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for key in ("key", "meaning", "mechanism", "decision", "priority", "consequence"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                errors.append(f"{prefix}.{key} must be nonempty text")
        key = entry.get("key")
        if isinstance(key, str):
            if key in seen:
                errors.append(f"{prefix} duplicates key {key}")
            seen.add(key)
        if not isinstance(entry.get("exceptions"), list) or any(not isinstance(x, str) for x in entry["exceptions"]):
            errors.append(f"{prefix}.exceptions must be a text list")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{prefix}.evidence must link sources, claims or workflow steps")
        else:
            for reference in evidence:
                if not isinstance(reference, str) or reference not in source_ids | workflow_ids:
                    errors.append(f"{prefix} unknown evidence {reference}")
    return errors


def capability_report(kit: Kit) -> dict:
    return {"capabilities": [{"id": tool.id, "readiness": tool.readiness,
                              "why": tool.why, "inputs": tool.inputs,
                              "outputs": tool.outputs, "access": tool.access,
                              "setup": tool.setup, "verification": tool.verification}
                             for tool in kit.capabilities],
            "gaps": list(kit.gaps), "execution_rights": "host authorization required"}
