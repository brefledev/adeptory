"""Checks cover the package's explicitly declared asset-removal rules."""
from .model import CheckResult
from .select import is_adopted


def check_consequences(kit, action, observations):
    if not is_adopted(kit):
        return CheckResult("allow", "Current version requires adoption before its rules activate.")
    if not isinstance(action, dict):
        return CheckResult("unknown", "Supply an operation and asset for declared coverage.")
    if action.get("operation") not in {"delete", "remove", "unlink"}:
        return CheckResult("allow", "Action falls outside declared asset-removal coverage.")
    asset = action.get("asset")
    if not isinstance(asset, str) or not asset:
        return CheckResult("unknown", "Asset-removal check requires an exact asset identifier.")
    rules = [r for r in kit.rules if r.get("kind") == "asset-removal" and r.get("asset") == asset]
    if not rules:
        return CheckResult("allow", "No declared removal rule covers this asset.")
    matching = [o for o in observations if o.kit_id == kit.id and o.subject == kit.subject
                and o.status == "unverified" and asset in (o.text + " " + o.evidence + " " + " ".join(o.keywords))]
    details = "; ".join(o.text + " Evidence: " + o.evidence for o in matching)
    return CheckResult("ask", "Check downstream references before removing " + asset + ". "
                       + (details or "Reference evidence remains a gap."),
                       [r["id"] for r in rules], [o.id for o in matching])
