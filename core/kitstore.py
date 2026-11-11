"""Versioned profile data with explicit adoption and inspectable exports."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import fields, MISSING
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from .model import (AdoptionRecord, Claim, Kit, KitError, SCHEMA_VERSION,
                    SourceRecord, ToolCapability, WorkflowStep, valid_id)
from .maps import map_errors
from .provenance import source_errors, review_errors, timestamp_valid


def _record(cls, data):
    if not isinstance(data, dict):
        raise KitError(f"{cls.__name__} must be an object")
    names = {f.name for f in fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise KitError(f"{cls.__name__} unsupported fields: {', '.join(str(key) for key in sorted(unknown, key=str))}")
    missing = [f.name for f in fields(cls) if f.default is MISSING and
               f.default_factory is MISSING and f.name not in data]
    if missing:
        raise KitError(f"{cls.__name__} missing fields: {', '.join(missing)}")
    return cls(**deepcopy(data))


def kit_from_dict(data: dict) -> Kit:
    kit = _record(Kit, data)
    for name, cls in (("sources", SourceRecord), ("claims", Claim),
                      ("workflow", WorkflowStep), ("capabilities", ToolCapability)):
        records = getattr(kit, name)
        if not isinstance(records, list):
            raise KitError(f"{name} must be a list")
        setattr(kit, name, [_record(cls, record) for record in records])
    kit.adoption = _record(AdoptionRecord, kit.adoption)
    errors = validate_kit(kit)
    if errors:
        raise KitError("invalid kit: " + "; ".join(errors))
    return kit


def validate_kit(kit: Kit) -> list[str]:
    errors = []
    if not isinstance(kit, Kit):
        return ["kit must be a Kit record"]
    try:
        valid_id(kit.id)
    except KitError as exc:
        errors.append(str(exc))
    if type(kit.schema_version) is not int or kit.schema_version != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")
    if type(kit.version) is not int or kit.version < 1:
        errors.append("version must be a positive integer")
    if type(kit.fixture) is not bool:
        errors.append("fixture must be boolean")
    for name in ("goal", "subject"):
        if not isinstance(getattr(kit, name), str) or not getattr(kit, name).strip():
            errors.append(f"{name} must be nonempty text")
    if not isinstance(kit.scope, dict):
        errors.append("scope must be an object")
    groups = (("sources", SourceRecord), ("claims", Claim),
              ("workflow", WorkflowStep), ("capabilities", ToolCapability))
    ids = {}
    for name, cls in groups:
        records = getattr(kit, name)
        ids[name] = set()
        if not isinstance(records, list):
            errors.append(f"{name} must be a list")
            continue
        for record in records:
            if not isinstance(record, cls):
                errors.append(f"{name} must contain {cls.__name__} records")
                continue
            try:
                valid_id(record.id)
            except KitError as exc:
                errors.append(f"{name}: {exc}")
                continue
            if record.id in ids[name]:
                errors.append(f"{name} duplicate id {record.id}")
            ids[name].add(record.id)
    for name in ("pending_choices", "gaps"):
        value = getattr(kit, name)
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            errors.append(f"{name} must be a list of nonempty text")
    if not isinstance(kit.rules, list) or any(not isinstance(x, dict) for x in kit.rules):
        errors.append("rules must be a list of objects")
    if not isinstance(kit.data_map, list):
        errors.append("data_map must be a list")
    if errors:
        return errors
    for source in kit.sources:
        if not isinstance(source.url, str) or not isinstance(source.excerpt, str):
            errors.append(f"source {source.id}: url and excerpt must be text")
            continue
        if not isinstance(source.limitations, list) or any(not isinstance(x, str) for x in source.limitations):
            errors.append(f"source {source.id}: limitations must be a text list")
        if source.jurisdiction is not None and not isinstance(source.jurisdiction, str):
            errors.append(f"source {source.id}: jurisdiction must be text")
        errors.extend(f"source {source.id}: {error}" for error in source_errors(source))
    sources = {source.id: source for source in kit.sources}
    for claim in kit.claims:
        for name in ("text",):
            if not isinstance(getattr(claim, name), str) or not getattr(claim, name).strip():
                errors.append(f"claim {claim.id}: {name} must be nonempty text")
        if type(claim.inference) is not bool or not isinstance(claim.review, dict):
            errors.append(f"claim {claim.id}: inference must be boolean and review an object")
        for name in ("source_ids", "contradictions"):
            if not isinstance(getattr(claim, name), list) or any(not isinstance(x, str) for x in getattr(claim, name)):
                errors.append(f"claim {claim.id}: {name} must be a text list")
        if not errors:
            errors.extend(f"claim {claim.id}: {error}" for error in review_errors(claim, sources))
    for step in kit.workflow:
        for name in ("instruction", "reason", "priority", "consequence"):
            if not isinstance(getattr(step, name), str) or not getattr(step, name).strip():
                errors.append(f"workflow {step.id}: {name} must be nonempty text")
        for name in ("evidence_requirements", "exceptions", "claim_ids", "keywords"):
            value = getattr(step, name)
            if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                errors.append(f"workflow {step.id}: {name} must be a text list")
        if isinstance(step.claim_ids, list):
            if not step.claim_ids:
                errors.append(f"workflow {step.id}: claim_ids must link researched rationale")
            for reference in step.claim_ids:
                if isinstance(reference, str) and reference not in ids["claims"]:
                    errors.append(f"workflow {step.id}: unknown claim {reference}")
    for tool in kit.capabilities:
        if tool.readiness not in ("available", "configurable", "build-required", "missing"):
            errors.append(f"capability {tool.id}: invalid readiness")
        for name in ("why", "verification"):
            if not isinstance(getattr(tool, name), str) or not getattr(tool, name).strip():
                errors.append(f"capability {tool.id}: {name} must be nonempty text")
        for name in ("inputs", "outputs", "access", "setup"):
            value = getattr(tool, name)
            if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                errors.append(f"capability {tool.id}: {name} must be a text list")
        if tool.readiness != "available" and not tool.setup:
            errors.append(f"capability {tool.id}: setup plan required")
    errors.extend(map_errors(kit.data_map, ids["sources"] | ids["claims"], ids["workflow"]))
    adoption = kit.adoption
    if not isinstance(adoption, AdoptionRecord):
        return errors + ["adoption must be an AdoptionRecord"]
    if adoption.status not in ("proposed", "adopted", "declined", "needs choice"):
        errors.append("adoption has unsupported status")
    if not isinstance(adoption.choices, dict):
        errors.append("adoption choices must be an object")
    if adoption.status == "adopted":
        if adoption.version != kit.version or type(adoption.version) is not int:
            errors.append("adoption version must match kit version")
        if adoption.origin not in ("verified-user-command", "verified-user-build-request", "fixture-harness"):
            errors.append("adoption requires trusted command origin")
        if adoption.origin == "fixture-harness" and not kit.fixture:
            errors.append("fixture adoption requires fixture kit")
        if not isinstance(adoption.actor, str) or not adoption.actor.strip() or not timestamp_valid(adoption.at):
            errors.append("adoption requires actor and ISO timestamp")
        if any(choice not in adoption.choices or adoption.choices[choice] is None or adoption.choices[choice] == ""
               for choice in kit.pending_choices):
            errors.append("adoption requires decisions for pending choices")
    try:
        json.dumps(kit.to_dict(), allow_nan=False)
    except (TypeError, ValueError):
        errors.append("kit must contain finite JSON data")
    return errors


def _content(kit):
    data = kit.to_dict()
    data.pop("adoption")
    data.pop("version")
    return data


class KitStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._path("kits").mkdir(exist_ok=True)

    def _path(self, *parts):
        path = self.root.joinpath(*parts)
        if not path.resolve().is_relative_to(self.root):
            raise KitError("storage path escapes plugin data root")
        return path

    def _kit_path(self, kit_id):
        valid_id(kit_id)
        if kit_id in {"con", "prn", "aux", "nul"} or kit_id in {f"{prefix}{digit}" for prefix in ("com", "lpt") for digit in range(1, 10)}:
            raise KitError("kit identifier is a reserved Windows device name")
        return self._path("kits", kit_id, "kit.json")

    @contextmanager
    def _lock(self):
        path = self._path(".adeptory-write.lock")
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise KitError("another writer holds the kit store; retry after it finishes") from exc
        try:
            os.close(descriptor)
            yield
        finally:
            path.unlink()

    @staticmethod
    def _write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".adeptory-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, kit_id):
        path = self._kit_path(kit_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KitError(f"cannot load kit {kit_id}: {exc}") from exc
        kit = kit_from_dict(data)
        if kit.id != kit_id:
            raise KitError("stored kit identity differs from requested identity")
        return kit

    def save(self, kit):
        content = deepcopy(kit)
        content.adoption = AdoptionRecord()
        errors = validate_kit(content)
        if errors:
            raise KitError("invalid kit: " + "; ".join(errors))
        kit = deepcopy(kit)
        with self._lock():
            path = self._kit_path(kit.id)
            if path.exists():
                previous = self.load(kit.id)
                if kit.version != previous.version:
                    raise KitError("stale or externally advanced revision; load current version before saving")
                if _content(kit) == _content(previous):
                    if kit.adoption != previous.adoption:
                        raise KitError("save cannot change adoption; use verified user command")
                    return previous
                if kit.fixture != previous.fixture:
                    raise KitError("fixture identity is immutable")
                history = self._path("kits", kit.id, "history", f"{previous.version}.json")
                self._write(history, previous.to_dict())
                kit.version = previous.version + 1
            elif kit.version != 1:
                raise KitError("new kit must begin at version 1")
            elif kit.adoption.status != "proposed" or kit.adoption.origin != "none":
                raise KitError("new kit adoption must be proposed")
            kit.adoption = AdoptionRecord()
            self._write(path, kit.to_dict())
        return kit

    def list(self):
        return [self.load(path.name) for path in sorted(self._path("kits").iterdir()) if path.is_dir()]

    def adopt(self, kit_id, *, origin, actor, choices=None, fixture_harness=False):
        if origin not in ("verified-user-command", "verified-user-build-request") and not (origin == "fixture-harness" and fixture_harness is True):
            raise KitError("adoption requires a verified user command or isolated fixture harness")
        if not isinstance(actor, str) or not actor.strip():
            raise KitError("adoption requires an identified actor")
        if choices is not None and not isinstance(choices, dict):
            raise KitError("choices must be an object")
        with self._lock():
            kit = self.load(kit_id)
            if origin == "fixture-harness" and not kit.fixture:
                raise KitError("fixture harness can adopt only fixture:true kits")
            chosen = deepcopy(choices or {})
            missing = [choice for choice in kit.pending_choices if choice not in chosen or chosen[choice] is None or chosen[choice] == ""]
            if missing:
                raise KitError("pending choices require user decisions: " + ", ".join(missing))
            kit.adoption = AdoptionRecord("adopted", origin, actor,
                datetime.now(timezone.utc).isoformat(), kit.version, chosen)
            errors = validate_kit(kit)
            if errors:
                raise KitError("invalid adoption: " + "; ".join(errors))
            self._write(self._kit_path(kit_id), kit.to_dict())
        return kit

    def export(self, kit_id, destination):
        kit = self.load(kit_id)
        destination = Path(destination).absolute()
        if destination.is_symlink():
            raise KitError("export destination must be a regular directory")
        destination = destination.resolve()
        if destination == self.root or destination.is_relative_to(self.root) or self.root.is_relative_to(destination):
            raise KitError("export destination must be separate from profile storage")
        if any(part.lower() in ("evals", ".git") for part in destination.parts):
            raise KitError("export destination is reserved")
        if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
            raise KitError("export destination must be empty")
        destination.mkdir(parents=True, exist_ok=True)
        import yaml
        data = kit.to_dict()
        (destination / "kit.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        (destination / "charter.md").write_text(
            f"# {kit.id}\n\n{kit.goal}\n\nSubject: {kit.subject}\n\n"
            + "Scope and boundaries\n\n```json\n" + json.dumps(kit.scope, indent=2) + "\n```\n\n"
            + "Uncertainty and escalation\n\n" + "\n".join(f"- {gap}" for gap in kit.gaps) + "\n", encoding="utf-8")
        for directory, value in (("workflows", data["workflow"]), ("maps", data["data_map"]),
                                 ("tools", data["capabilities"]), ("sources", data["sources"]),
                                 ("decisions", {"adoption": data["adoption"], "pending_choices": data["pending_choices"]})):
            (destination / directory).mkdir()
            self._write(destination / directory / "records.json", value)
        self._write(destination / "sources" / "claims.json", data["claims"])
        (destination / 'runtime').mkdir(exist_ok=True)
        (destination / 'runtime' / 'SOUL.md').write_text(
            f'# Specialist\n\nGoal: {kit.goal}\n\nSubject: {kit.subject}\n\n'
            'Use the profile-owned library for relevant knowledge and procedures. '
            f'The profile home contains library/{kit.id}/_index.md and readable references, procedures and examples. '
            'Use normal file search and full-entry reads for direct retrieval from those files. '
            f'With Adeptory enabled, search adeptory_library with kit_id {kit.id} and the task terms. '
            'Read complete entries with their applicability, exceptions, source dates and dependencies. '
            'Treat originals as evidence. Check changed or review-due sources before consequential reliance. '
            'Use adopted procedures and observed tools. Ask focused questions about consequential unknowns.\n', encoding='utf8')
        library = getattr(self, 'library', None)
        if library is not None and library.directory(kit.id).exists():
            import shutil
            origin = library.directory(kit.id)
            for candidate in origin.rglob('*'):
                if candidate.is_symlink() or not candidate.resolve().is_relative_to(origin.resolve()):
                    raise KitError('library export contains an escaping path')
            shutil.copytree(origin, destination / 'library' / kit.id)
            (destination / 'library' / '_index.md').write_text(
                f'# Profile library\n\n- [{kit.goal}]({kit.id}/_index.md)\n', encoding='utf8')
        (destination / "tests").mkdir()
        (destination / "tests" / "README.md").write_text("Record task-specific checks and results here. Evaluation cases remain in a separate evaluation workspace.\n", encoding="utf-8")
        history = self._path("kits", kit.id, "history")
        (destination / "history").mkdir()
        if history.exists():
            for path in sorted(history.glob("*.json")):
                if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                    raise KitError("history path escapes profile storage")
                self._write(destination / "history" / path.name, json.loads(path.read_text(encoding="utf-8")))
        return destination
