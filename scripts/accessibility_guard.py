#!/usr/bin/env python3
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


class AuditParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.labels: set[str] = set()
        self.controls: list[tuple[str, dict[str, str | None], bool]] = []
        self.images: list[dict[str, str | None]] = []
        self.references: list[tuple[str, str]] = []
        self.stack: list[str] = []
        self.label_depth = 0
        self.button_text: list[str] = []
        self.html_lang = None

    def handle_starttag(self, tag: str, attrs_list):
        attrs = dict(attrs_list)
        self.stack.append(tag)
        if tag == "html":
            self.html_lang = attrs.get("lang")
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag == "label":
            self.label_depth += 1
            if attrs.get("for"):
                self.labels.add(attrs["for"])
        if tag in ("input", "select", "textarea"):
            self.controls.append((tag, attrs, self.label_depth > 0))
        if tag == "button":
            self.controls.append((tag, attrs, False))
            self.button_text.append("")
        if tag == "img":
            self.images.append(attrs)
        for attribute in ("aria-labelledby", "aria-describedby"):
            if attrs.get(attribute):
                for target in attrs[attribute].split():
                    self.references.append((attribute, target))

    def handle_data(self, data: str):
        if self.button_text and "button" in self.stack:
            self.button_text[-1] += data

    def handle_endtag(self, tag: str):
        if tag == "label":
            self.label_depth -= 1
        if self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag) if tag in self.stack else len(self.stack) - 1
            self.stack = self.stack[:index]


def audit() -> list[str]:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    parser = AuditParser()
    parser.feed(html)
    failures: list[str] = []
    duplicates = sorted({value for value in parser.ids if parser.ids.count(value) > 1})
    if duplicates:
        failures.append(f"duplicate ids: {duplicates}")
    id_set = set(parser.ids)
    for attribute, target in parser.references:
        if target not in id_set:
            failures.append(f"{attribute} references missing id {target!r}")
    for tag, attrs, nested_label in parser.controls:
        if tag == "input" and (attrs.get("type") == "hidden" or "hidden" in attrs):
            continue
        if tag == "button":
            continue
        control_id = attrs.get("id")
        if not attrs.get("aria-label") and not nested_label and (not control_id or control_id not in parser.labels):
            failures.append(f"unlabelled {tag} id={control_id!r} name={attrs.get('name')!r}")
    for index, attrs in enumerate(parser.images):
        if "alt" not in attrs:
            failures.append(f"image {index + 1} has no alt attribute")
    for index, match in enumerate(re.finditer(r"(?is)<button\b([^>]*)>(.*?)</button>", html), 1):
        attributes, content = match.groups()
        visible_text = re.sub(r"(?is)<[^>]+>", "", content).strip()
        if not visible_text and not re.search(r"\baria-label\s*=", attributes, re.I):
            failures.append(f"button {index} has no text or aria-label")
    if parser.html_lang != "en":
        failures.append("html lang must be 'en'")
    required_fragments = (
        'class="skip-link" href="#main" inert aria-hidden="true"',
        'class="topbar" inert aria-hidden="true"',
        'class="shell" inert aria-hidden="true"',
        'id="main" tabindex="-1"',
        'id="toast" role="status" aria-live="polite"',
    )
    for fragment in required_fragments:
        if fragment not in html:
            failures.append(f"missing accessibility contract: {fragment}")
    for fragment in (":focus-visible", "prefers-reduced-motion"):
        if fragment not in css:
            failures.append(f"styles missing {fragment}")
    return failures


def main() -> int:
    failures = audit()
    if failures:
        print("ACCESSIBILITY CHECK FAILED")
        print("\n".join(failures))
        return 1
    print("ACCESSIBILITY CHECK PASSED: static semantics, labels, references, auth isolation, focus and motion contracts are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
