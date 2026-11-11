"""Resumable generic intake and proposal operations for host research tools."""
from copy import deepcopy
import json
from pathlib import Path
import uuid

from .kitstore import KitStore, kit_from_dict, _content
from .model import AdoptionRecord, Kit, KitError, SourceRecord, valid_id
from .provenance import provenance_report
from .maps import capability_report
from .library import KnowledgeLibrary
from .buildplan import BuildPlan


def read_proposal(path, *, allowed_root):
    """Read user-selected package data within an explicit generator workspace."""
    root = Path(allowed_root).resolve()
    target = Path(path).resolve()
    if not target.is_relative_to(root):
        raise KitError("proposal import must stay within generator workspace")
    if any(part.lower() in ("evals", "evaluations", "held-out", "held_out", ".git") for part in target.parts):
        raise KitError("evaluation and repository metadata are excluded from generator inputs")
    try:
        text = target.read_text(encoding="utf-8")
        if target.suffix.lower() == ".json":
            return json.loads(text)
        if target.suffix.lower() in (".yaml", ".yml"):
            import yaml
            return yaml.safe_load(text)
        raise KitError("proposal file must be JSON or YAML")
    except (OSError, ValueError) as exc:
        raise KitError(f"cannot read proposal: {exc}") from exc


def readiness_gaps(kit):
    gaps = []
    primary = [source for source in kit.sources if source.quality == "primary"]
    if not primary:
        gaps.append("Capture authoritative sources appropriate to the specialist's knowledge requirements.")
    if not any(claim.source_ids and claim.support == 'supported' for claim in kit.claims):
        gaps.append("Draft researched claims with source links and semantic support reviews.")
    if any(claim.support != "supported" for claim in kit.claims):
        gaps.append("Resolve unsupported claim reasoning or scope it to what the sources support.")
    if not kit.workflow:
        gaps.append("Draft the bounded workflow, rationale, exceptions, priorities and consequences.")
    if not any(tool.readiness == "available" for tool in kit.capabilities):
        gaps.append("Record an observed available read-only tool or workflow with its verification method.")
    if any(tool.readiness != 'available' and not tool.setup for tool in kit.capabilities):
        gaps.append('Document the setup or engineering work for each unavailable required capability.')
    gaps.extend(kit.gaps)
    return gaps


class Builder:
    def __init__(self, store: KitStore, library=None):
        self.store = store
        self.library = library or KnowledgeLibrary(store.root / 'library')
        self.store.library = self.library
        self.plans = BuildPlan(self.library)
        self.library.on_change = self.bind_library

    def bind_library(self, kit_id):
        """A meaningful library revision participates in the existing adoption/version boundary."""
        status = self.library.status(kit_id)
        if not status['documents'] and not status['entries']:
            return
        kit = self.store.load(kit_id)
        fingerprint = self.library.fingerprint(kit_id)
        if kit.scope.get('library_fingerprint') != fingerprint:
            kit.scope['library_fingerprint'] = fingerprint
            self.store.save(kit)

    def start(self, goal, subject, scope=None, fixture=False):
        kit = Kit(id="kit-" + uuid.uuid4().hex[:16], goal=goal, subject=subject,
                  scope=deepcopy(scope or {}), fixture=fixture)
        saved = self.store.save(kit)
        self.library.initialize(saved.id, saved.goal, saved.subject)
        self.plans.update(saved.id, {})
        return saved

    def propose(self, data):
        if not isinstance(data, dict):
            raise KitError("proposal must be a full kit object")
        proposed = deepcopy(data)
        if "adoption" in proposed:
            adoption = proposed["adoption"]
            if not isinstance(adoption, dict) or adoption.get("status", "proposed") != "proposed" or adoption.get("origin", "none") != "none":
                raise KitError("model proposals must keep adoption proposed with origin none")
        if proposed.get("id") and self.store._kit_path(proposed["id"]).exists():
            if "version" not in proposed:
                raise KitError("updating a kit requires its current version")
            current_data = self.store.load(proposed["id"]).to_dict()
            current_data.update(proposed)
            proposed = current_data
        proposed["adoption"] = AdoptionRecord().__dict__
        kit = kit_from_dict(proposed)
        path = self.store._kit_path(kit.id)
        if path.exists():
            current = self.store.load(kit.id)
            if kit.version != current.version:
                raise KitError("proposal version is stale; reload the current kit")
            if _content(kit) == _content(current):
                kit.adoption = current.adoption
        saved = self.store.save(kit)
        self.library.initialize(saved.id, saved.goal, saved.subject)
        return saved

    def source(self, kit_id, data):
        if not isinstance(data, dict):
            raise KitError("source must be a captured source object")
        kit = self.store.load(valid_id(kit_id))
        source_data = deepcopy(data)
        try:
            source = SourceRecord(**source_data)
        except TypeError as exc:
            raise KitError(f"source schema: {exc}") from exc
        existing = next((index for index, item in enumerate(kit.sources) if item.id == source.id), None)
        if existing is None:
            kit.sources.append(source)
        else:
            old = kit.sources[existing]
            if old != source:
                for claim in kit.claims:
                    if source.id in claim.source_ids:
                        claim.support = "unverified"
                        claim.review = {}
                kit.sources[existing] = source
        return self.store.save(kit)

    def status(self, kit_id):
        kit = self.store.load(kit_id)
        self.store.sync_capability_roadmap(kit.id)
        gaps = readiness_gaps(kit)
        construction = self.plans.progress(kit.id)
        if not construction['plan']['outcomes']:
            gaps.append('Define useful work and its acceptance evidence in the construction plan.')
        if not construction['plan']['requirements']:
            gaps.append('Identify the specialist knowledge requirements and applicable source roles.')
        if construction['unresolved_requirements']:
            gaps.append('Acquire or explicitly scope out unresolved knowledge requirements.')
        if not construction['library']['entries']:
            gaps.append('Build the searchable source-linked specialist library.')
        knowledge_gaps = gaps + construction['knowledge_completion_gaps']
        gaps.extend(construction['completion_gaps'])
        next_task = construction['next_executable_task']
        if (gaps and next_task is None and construction['required_tasks_complete']
                and not construction['user_blockers']):
            next_task = {'id': 'readiness', 'description': gaps[0], 'status': 'pending',
                         'blocked_by': [], 'evidence': [], 'kind': 'readiness-gap'}
        if gaps:
            stage = 'building'
        elif kit.adoption.status == "adopted" and kit.adoption.version == kit.version:
            stage = "adopted"
        elif kit.pending_choices:
            stage = "needs choice"
        else:
            stage = "review"
        return {"id": kit.id, "version": kit.version, "stage": stage,
                "goal": kit.goal, "subject": kit.subject, "scope": kit.scope,
                "fixture": kit.fixture, "adoption": kit.to_dict()["adoption"],
                "pending_choices": kit.pending_choices, "gaps": gaps,
                "ready_for_review": not gaps,
                "ready_for_bundle": not knowledge_gaps,
                "knowledge_completion_gaps": knowledge_gaps,
                "completion_gaps": gaps,
                "next_executable_task": next_task,
                "user_blockers": construction['user_blockers'],
                "provenance": provenance_report(kit),
                "tools": capability_report(kit),
                "construction": construction,
                "next_action": {
                    "building": ('Continue construction: ' + next_task['description']
                                 if next_task else 'Resolve the recorded blockers for unfinished construction tasks.'),
                    "needs choice": "Present the package and ask the user to decide pending substantive choices.",
                    "review": "Present source support, gaps and capability limits for user review.",
                    "adopted": "Use the completed specialist on the requested task, retaining its source qualifications and host permissions."
                }[stage]}
