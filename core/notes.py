"""Expiring, dismissible observations, scoped to a kit and subject."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from .model import KitError, Observation, valid_id
from .select import terms


def timestamp(value):
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise KitError("observation timestamps require a timezone")
    return moment.astimezone(timezone.utc)


class NoteStore:
    def __init__(self, root):
        self.root = Path(root) / "notes"

    def add(self, observation):
        if isinstance(observation, dict):
            observation = Observation(**observation)
        valid_id(observation.id)
        valid_id(observation.kit_id)
        if not all(isinstance(x, str) and x.strip() for x in
                   [observation.subject, observation.text, observation.evidence, observation.origin]):
            raise KitError("observation requires subject, text, evidence and origin")
        if observation.status != "unverified":
            raise KitError("observations enter as unverified leads")
        if timestamp(observation.expires_at) <= timestamp(observation.at):
            raise KitError("observation expiry must follow capture")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (observation.id + ".json")
        if path.exists():
            raise KitError("observation id already exists")
        self._write(path, asdict(observation))
        return observation

    def _write(self, path, value):
        temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def relevant(self, kit_id, subject, task):
        valid_id(kit_id)
        now = datetime.now(timezone.utc)
        found = []
        for path in sorted(self.root.glob("*.json")):
            try:
                note = Observation(**json.loads(path.read_text(encoding="utf-8")))
                if (note.kit_id == kit_id and note.subject == subject
                        and note.status == "unverified" and timestamp(note.expires_at) > now
                        and terms(task) & terms(" ".join(note.keywords) + " " + note.text)):
                    found.append(note)
            except (ValueError, TypeError, OSError) as exc:
                raise KitError(f"malformed observation state {path.name}: {exc}") from exc
        return found

    def dismiss(self, note_id):
        valid_id(note_id)
        path = self.root / (note_id + ".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "dismissed"
        self._write(path, data)
