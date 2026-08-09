from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

from test3.warehouse.storage import WarehousePaths


@dataclass(frozen=True)
class ImportMappingTemplate:
    template_id: str
    version: str
    expected_columns: tuple[str, ...]
    column_mapping: dict[str, str]
    defaults: dict[str, object]
    source_name: str
    licensing_notes: str

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", self.template_id):
            raise ValueError("template_id must be a safe governed identifier")
        if not self.licensing_notes.strip() or not self.source_name.strip():
            raise ValueError("source name and licensing notes are required")
        if set(self.column_mapping) - set(self.expected_columns):
            raise ValueError("mapping references columns outside expected_columns")
        targets = list(self.column_mapping.values())
        if len(targets) != len(set(targets)):
            raise ValueError("two input columns cannot map to the same canonical field")


def apply_mapping(rows: list[dict], template: ImportMappingTemplate) -> list[dict]:
    template.validate()
    if not rows:
        raise ValueError("source file is empty")
    actual = tuple(str(item) for item in rows[0])
    if set(actual) != set(template.expected_columns):
        raise ValueError("source columns do not exactly match the saved mapping template")
    output = []
    for row in rows:
        mapped = dict(template.defaults)
        mapped.update({target: row.get(source) for source, target in template.column_mapping.items()})
        mapped.setdefault("source_name", template.source_name)
        mapped.setdefault("licensing_notes", template.licensing_notes)
        output.append(mapped)
    return output


def save_mapping(paths: WarehousePaths, template: ImportMappingTemplate) -> Path:
    template.validate(); paths.initialize()
    payload = asdict(template)
    payload["expected_columns"] = list(template.expected_columns)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    directory = paths.contained(Path("manifests") / "cre_import_mappings" / template.template_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{template.version}-{digest[:12]}.json"
    if destination.exists():
        return destination
    destination.write_text(json.dumps({**payload, "sha256": digest}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def load_mapping(path: str | Path) -> ImportMappingTemplate:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    stored = payload.pop("sha256", None)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if stored != digest:
        raise ValueError("import mapping integrity failure")
    return ImportMappingTemplate(**{**payload, "expected_columns": tuple(payload["expected_columns"])})
