"""Pass compiler. One pass YAML produces the prompt, the response schema, and
the post-hoc validator (rule 6.10). Nothing else defines any of the three.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from closeread.config import REPO_ROOT

PASSES_DIR = REPO_ROOT / "schemas" / "passes"
VOCAB_DIR = REPO_ROOT / "schemas" / "vocabularies"


@dataclass
class AttrSpec:
    name: str
    type: str = "string"
    vocabulary: str | None = None
    values: list[str] = field(default_factory=list)  # resolved vocabulary values


@dataclass
class ClassDef:
    name: str
    description: str
    attributes: dict[str, AttrSpec]
    examples: list[dict[str, Any]]
    # When set, collect writes an explicit absence record with these
    # attributes for any document that yields zero records of this class
    # (rule 6.3: record absence, do not write nothing).
    absence_attributes: dict[str, Any] | None = None


@dataclass
class CompiledPass:
    name: str
    version: str
    applies_to: list[str]
    sections: list[str] | None
    window_chars: int
    classes: dict[str, ClassDef]

    # ---- prompt ----------------------------------------------------------
    def prompt(self, document_text: str) -> str:
        lines: list[str] = [
            "You are extracting structured, evidence-linked facts from the text of a scientific publication.",
            "",
            "Extract facts for the classes defined below. Return JSON only, matching the response schema.",
            "",
            "Rules:",
            "1. source_quote must be a VERBATIM substring of the document text, copied exactly,",
            "   including punctuation and capitalisation. Never paraphrase, never shorten with",
            "   ellipses, never merge separate sentences. Keep quotes under 300 characters.",
            "2. Every attribute key must appear in the output. Use \"not_stated\" when the text",
            "   does not give a value. Never combine several attributes into one string.",
            "3. Where an attribute lists allowed values, prefer them. If the text states a value",
            "   that is genuinely outside the list, give the value as written in the text.",
            "4. One record per distinct fact. Return an empty list for a class when the document",
            "   states nothing for it.",
            "5. Extract only what this document states. Do not use outside knowledge.",
            "",
            "Classes:",
        ]
        for cls in self.classes.values():
            lines.append(f"\n## {cls.name}")
            lines.append(cls.description.strip())
            lines.append("Attributes:")
            for attr in cls.attributes.values():
                if attr.values:
                    lines.append(f"- {attr.name}: one of {json.dumps(attr.values)}")
                else:
                    lines.append(f"- {attr.name}: free text, verbatim from the document where possible")
            if cls.examples:
                lines.append("Examples:")
                for ex in cls.examples:
                    expected = [
                        {"source_quote": e["span"], **{k: v for k, v in e.items() if k != "span"}}
                        for e in ex["extractions"]
                    ]
                    lines.append(f'Text: "{ex["text"]}"')
                    lines.append(f"Output: {json.dumps({cls.name: expected}, ensure_ascii=False)}")
        lines += [
            "",
            "Document text:",
            "<<<",
            document_text,
            ">>>",
        ]
        return "\n".join(lines)

    # ---- response schema -------------------------------------------------
    def response_schema(self) -> dict[str, Any]:
        """Gemini responseSchema (proto-shaped, camelCase context; §3.3/§3.4).

        Vocabularies are deliberately NOT enforced as enums here: rule 6.5
        requires out-of-vocabulary values to surface as enum_drift, not be
        forced into the closed list. The validator computes drift post hoc.
        """
        properties: dict[str, Any] = {}
        for cls in self.classes.values():
            item_props: dict[str, Any] = {"source_quote": {"type": "STRING"}}
            item_props.update({a: {"type": "STRING"} for a in cls.attributes})
            properties[cls.name] = {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": item_props,
                    "required": ["source_quote", *cls.attributes],
                },
            }
        return {
            "type": "OBJECT",
            "properties": properties,
            "required": list(self.classes),
        }

    # ---- validator ---------------------------------------------------------
    def validate_response(self, parsed: dict[str, Any]) -> list[str]:
        """Structural issues with a parsed response. Empty list = valid."""
        issues: list[str] = []
        if not isinstance(parsed, dict):
            return ["response is not a JSON object"]
        for cls_name in self.classes:
            if cls_name not in parsed:
                issues.append(f"missing class key: {cls_name}")
                continue
            if not isinstance(parsed[cls_name], list):
                issues.append(f"class {cls_name} is not a list")
                continue
            for i, item in enumerate(parsed[cls_name]):
                if not isinstance(item, dict):
                    issues.append(f"{cls_name}[{i}] is not an object")
                    continue
                if not item.get("source_quote"):
                    issues.append(f"{cls_name}[{i}] missing source_quote")
                for attr in self.classes[cls_name].attributes:
                    if attr not in item:
                        issues.append(f"{cls_name}[{i}] missing attribute {attr}")
        return issues

    def enum_drift(self, cls_name: str, attributes: dict[str, Any]) -> list[str]:
        """Attribute values outside their closed vocabulary (rule 6.5)."""
        drift: list[str] = []
        cls = self.classes[cls_name]
        for attr_name, spec in cls.attributes.items():
            if not spec.values:
                continue
            value = attributes.get(attr_name)
            if value is not None and str(value) not in spec.values:
                drift.append(f"{attr_name}={value}")
        return drift


def load_vocabulary(name: str) -> list[str]:
    with open(VOCAB_DIR / f"{name}.yaml") as fh:
        data = yaml.safe_load(fh)
    return [str(v) for v in data["values"]]


def load_pass(name_or_path: str | Path) -> CompiledPass:
    path = Path(name_or_path)
    if not path.exists():
        path = PASSES_DIR / f"{name_or_path}.yaml"
    with open(path) as fh:
        raw = yaml.safe_load(fh)

    classes: dict[str, ClassDef] = {}
    for cls_name, cls_raw in raw["classes"].items():
        attrs: dict[str, AttrSpec] = {}
        for attr_name, attr_raw in (cls_raw.get("attributes") or {}).items():
            vocab = attr_raw.get("vocabulary")
            attrs[attr_name] = AttrSpec(
                name=attr_name,
                type=attr_raw.get("type", "string"),
                vocabulary=vocab,
                values=load_vocabulary(vocab) if vocab else [],
            )
        classes[cls_name] = ClassDef(
            name=cls_name,
            description=cls_raw.get("description", ""),
            attributes=attrs,
            examples=cls_raw.get("examples") or [],
            absence_attributes=cls_raw.get("absence_attributes"),
        )
    return CompiledPass(
        name=raw["pass"],
        version=str(raw["version"]),
        applies_to=list(raw.get("applies_to") or []),
        sections=raw.get("sections"),
        window_chars=int(raw.get("window_chars", 30_000)),
        classes=classes,
    )
