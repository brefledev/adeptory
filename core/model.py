"""Versioned portable records. Evidence and adoption have separate owners."""
from dataclasses import asdict, dataclass, field
from typing import Any
import re

SCHEMA_VERSION = 1

class KitError(ValueError):
    pass

def valid_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise KitError("identifier must contain 1-64 lowercase letters, digits, underscores or hyphens")
    return value

@dataclass
class SourceRecord:
    id: str
    url: str
    title: str
    retrieved_at: str
    excerpt: str
    locator: str
    retrieval_tool: str
    effective_or_published: str | None = None
    quality: str = "primary"
    limitations: list[str] = field(default_factory=list)
    jurisdiction: str | None = None
    receipt: dict[str, Any] = field(default_factory=dict)

@dataclass
class Claim:
    id: str
    text: str
    source_ids: list[str]
    support: str = "unverified"
    review: dict[str, Any] = field(default_factory=dict)
    contradictions: list[str] = field(default_factory=list)
    inference: bool = False

@dataclass
class WorkflowStep:
    id: str
    instruction: str
    reason: str
    evidence_requirements: list[str]
    exceptions: list[str]
    priority: str
    consequence: str
    claim_ids: list[str]
    keywords: list[str] = field(default_factory=list)

@dataclass
class ToolCapability:
    id: str
    readiness: str
    why: str
    inputs: list[str]
    outputs: list[str]
    access: list[str]
    setup: list[str]
    verification: str

@dataclass
class AdoptionRecord:
    status: str = "proposed"
    origin: str = "none"
    actor: str | None = None
    at: str | None = None
    version: int | None = None
    choices: dict[str, Any] = field(default_factory=dict)

@dataclass
class Kit:
    id: str
    goal: str
    subject: str
    version: int = 1
    schema_version: int = SCHEMA_VERSION
    fixture: bool = False
    scope: dict[str, Any] = field(default_factory=dict)
    sources: list[SourceRecord] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    workflow: list[WorkflowStep] = field(default_factory=list)
    capabilities: list[ToolCapability] = field(default_factory=list)
    data_map: list[dict[str, Any]] = field(default_factory=list)
    pending_choices: list[str] = field(default_factory=list)
    adoption: AdoptionRecord = field(default_factory=AdoptionRecord)
    rules: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Observation:
    id: str
    kit_id: str
    subject: str
    text: str
    evidence: str
    origin: str
    at: str
    expires_at: str
    keywords: list[str] = field(default_factory=list)
    status: str = "unverified"

@dataclass
class CheckResult:
    decision: str
    message: str
    rule_ids: list[str] = field(default_factory=list)
    observation_ids: list[str] = field(default_factory=list)
    coverage: str = "declared rules only"
    host_authorization: str = "separate host permission required"

@dataclass
class EvalResult:
    case: str
    arm: str
    scores: dict[str, int]
    reasons: dict[str, str]
    model: str
    evidence: list[str]
    costs: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
