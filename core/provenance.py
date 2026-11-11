"""Check captured attribution independently of semantic claim review."""
from datetime import datetime
from hashlib import sha256
from urllib.parse import urlparse

from .model import Claim, SourceRecord


def timestamp_valid(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def source_errors(source: SourceRecord) -> list[str]:
    errors = []
    try:
        parsed = urlparse(source.url)
        valid_url = parsed.scheme in ("https", "http") and bool(parsed.hostname) and not parsed.username and not parsed.password
        parsed.port
    except ValueError:
        valid_url = False
    if not valid_url:
        errors.append("url must be an absolute HTTP(S) source without credentials")
    for name in ("title", "excerpt", "locator", "retrieval_tool"):
        if not isinstance(getattr(source, name), str) or not getattr(source, name).strip():
            errors.append(f"{name} must capture nonempty source metadata")
    if not timestamp_valid(source.retrieved_at):
        errors.append("retrieved_at must be an ISO date or timestamp")
    if source.effective_or_published is not None and not timestamp_valid(source.effective_or_published):
        errors.append("effective_or_published must be an ISO date or timestamp")
    if source.quality not in ("primary", "secondary", "user", "unknown"):
        errors.append("quality must be primary, secondary, user or unknown")
    if not isinstance(source.receipt, dict):
        errors.append("receipt must be an object")
        return errors
    receipt = source.receipt
    for key, expected in (("url", source.url), ("retrieved_at", source.retrieved_at),
                          ("retrieval_tool", source.retrieval_tool)):
        if key in receipt and receipt[key] != expected:
            errors.append(f"receipt {key} differs from source")
    if "excerpt_sha256" in receipt and receipt["excerpt_sha256"] != sha256(source.excerpt.encode()).hexdigest():
        errors.append("receipt excerpt_sha256 differs from captured passage")
    return errors


def attribution_receipt(source: SourceRecord) -> dict:
    """Describe inspectable passage capture; host authenticity stays a host concern."""
    errors = source_errors(source)
    return {"source_id": source.id, "url": source.url,
            "retrieved_at": source.retrieved_at, "retrieval_tool": source.retrieval_tool,
            "locator": source.locator,
            "excerpt_sha256": sha256(source.excerpt.encode()).hexdigest(),
            "status": "invalid" if errors else "captured",
            "errors": errors,
            "limitation": "Metadata and passage checks establish captured attribution. Host retrieval authenticity and semantic support require separate review."}


def review_errors(claim: Claim, sources: dict[str, SourceRecord]) -> list[str]:
    errors = []
    if claim.support not in ("supported", "partial", "contradicted", "unverified"):
        errors.append("support must be supported, partial, contradicted or unverified")
    if not claim.source_ids and not claim.inference:
        errors.append("researched claims require source_ids")
    for source_id in claim.source_ids:
        if source_id not in sources:
            errors.append(f"unknown source {source_id}")
    review = claim.review
    if claim.support != "unverified":
        if not isinstance(review, dict):
            return errors + ["semantic review must be an object"]
        if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
            errors.append("semantic review requires reviewer")
        if not isinstance(review.get("reason"), str) or not review["reason"].strip():
            errors.append("semantic review requires reason")
        checks = review.get("passage_checks")
        if not isinstance(checks, list) or not checks:
            errors.append("semantic review requires passage_checks")
        else:
            checked = set()
            for check in checks:
                if not isinstance(check, dict):
                    errors.append("passage check must be an object")
                    continue
                source_id = check.get("source_id")
                passage = check.get("passage")
                source = sources.get(source_id) if isinstance(source_id, str) else None
                if source_id not in claim.source_ids or source is None:
                    errors.append("passage check must reference a claim source")
                elif not isinstance(passage, str) or not passage.strip() or passage not in source.excerpt:
                    errors.append(f"passage check must match captured excerpt for {source_id}")
                else:
                    checked.add(source_id)
                if not isinstance(check.get("reason"), str) or not check["reason"].strip():
                    errors.append("passage check requires a support reason")
            if set(claim.source_ids) - checked:
                errors.append("semantic review must check every cited source passage")
    return errors


def provenance_report(kit) -> dict:
    return {"sources": [attribution_receipt(source) for source in kit.sources],
            "claims": [{"claim_id": claim.id, "support": claim.support,
                        "review": claim.review, "source_ids": claim.source_ids,
                        "contradictions": claim.contradictions,
                        "inference": claim.inference} for claim in kit.claims]}
