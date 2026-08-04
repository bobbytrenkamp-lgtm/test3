from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from .normalization import number

MAX_XLSX_ENTRIES = 250
MAX_XLSX_XML_BYTES = 25 * 1024 * 1024
MAX_XLSX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_XLSX_ROWS = 100_000
MAX_XLSX_CELLS = 2_000_000


@dataclass(frozen=True)
class Candidate:
    field: str
    raw: str
    normalized: str | None
    page: int | None
    excerpt: str
    confidence: float
    method: str
    bbox: tuple[float, float, float, float] | None = None


FIELD_PATTERNS = {
    "property_name": r"(?im)^property(?: name)?\s*[:,-]\s*(.+)$",
    "address": r"(?im)^address\s*[:,-]\s*(.+)$",
    "asking_price": r"(?i)(?:asking|purchase) price\s*[:$ ]+([($0-9,.]+)",
    "broker_stated_noi": r"(?i)(?:broker[- ]stated )?noi\s*[:$ ]+([($0-9,.]+)",
    "broker_stated_cap_rate": r"(?i)(?:cap(?:italization)? rate)\s*[: ]+([0-9.]+%?)",
    "rentable_square_feet": r"(?i)(?:rentable (?:area|square feet)|rsf)\s*[: ]+([0-9,.]+)",
    "occupancy": r"(?i)occupancy\s*[: ]+([0-9.]+%?)",
    "unit_count": r"(?i)(?:unit count|units)\s*[: ]+([0-9,]+)",
    "loan_amount": r"(?i)loan amount\s*[:$ ]+([($0-9,.]+)",
    "interest_rate": r"(?i)(?:all-in )?interest rate\s*[: ]+([0-9.]+%?)",
}


def extract_text_candidates(text: str, page: int = 1, method: str = "deterministic_regex_v1") -> list[Candidate]:
    candidates = []
    for field, pattern in FIELD_PATTERNS.items():
        match = re.search(pattern, text)
        if not match:
            continue
        raw = match.group(1).strip()[:500]
        numeric = number(raw)
        normalized = str(numeric) if numeric is not None else raw
        start, end = max(0, match.start() - 60), min(len(text), match.end() + 60)
        candidates.append(Candidate(field, raw, normalized, page, text[start:end].strip(), 0.82, method))
    return candidates


def parse_csv(content: bytes) -> tuple[list[list[str]], list[Candidate]]:
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    candidates = []
    if rows:
        headers = [re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") for value in rows[0]]
        for row_index, row in enumerate(rows[1:], 2):
            for index, raw in enumerate(row):
                if raw.strip() and index < len(headers):
                    candidates.append(Candidate(f"row.{row_index}.{headers[index] or index}", raw, str(number(raw)) if number(raw) is not None else raw.strip(), 1, f"CSV row {row_index}, column {index + 1}", 0.95, "csv_cell_v1", (index, row_index - 1, index + 1, row_index)))
    return rows, candidates


def parse_xlsx(content: bytes) -> tuple[list[list[str]], list[Candidate]]:
    # XLSX is a ZIP of XML. Values only are read; formulas, macros, links and scripts are never evaluated.
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_XLSX_ENTRIES:
            raise ValueError("XLSX archive contains too many entries")
        if sum(entry.file_size for entry in entries) > MAX_XLSX_TOTAL_BYTES:
            raise ValueError("XLSX expanded content exceeds the safety limit")
        for entry in entries:
            if entry.file_size > MAX_XLSX_XML_BYTES:
                raise ValueError("XLSX entry exceeds the safety limit")
            if entry.compress_size and entry.file_size / entry.compress_size > 200:
                raise ValueError("XLSX compression ratio is unsafe")
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root]
        sheet_name = next((name for name in sorted(names) if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")), None)
        if not sheet_name:
            return [], []
        root = ElementTree.fromstring(archive.read(sheet_name))
        rows = []
        row_nodes = [node for node in root.iter() if node.tag.endswith("}row")]
        if len(row_nodes) > MAX_XLSX_ROWS:
            raise ValueError("XLSX row count exceeds the safety limit")
        cell_count = 0
        for row in row_nodes:
            values = []
            cells = [node for node in row if node.tag.endswith("}c")]
            cell_count += len(cells)
            if cell_count > MAX_XLSX_CELLS:
                raise ValueError("XLSX cell count exceeds the safety limit")
            for cell in cells:
                value_node = next((node for node in cell.iter() if node.tag.endswith("}v")), None)
                value = value_node.text if value_node is not None and value_node.text else ""
                if cell.attrib.get("t") == "s" and value.isdigit() and int(value) < len(shared):
                    value = shared[int(value)]
                values.append(value)
            rows.append(values)
        csv_content = io.StringIO()
        csv.writer(csv_content).writerows(rows)
        return parse_csv(csv_content.getvalue().encode())


def extract_selectable_pdf_text(content: bytes) -> str:
    # Conservative fallback for simple PDFs. Complex PDFs remain visibly flagged for local OCR/manual review.
    chunks = []
    for match in re.finditer(rb"\(([^()]*)\)\s*Tj", content, re.DOTALL):
        raw = re.sub(rb"\\([()\\])", rb"\1", match.group(1))
        chunks.append(raw.decode("latin-1", errors="replace"))
    return "\n".join(chunks)


def process(filename: str, mime: str, content: bytes) -> tuple[str, list[Candidate], str | None]:
    if mime == "text/csv":
        _, candidates = parse_csv(content)
        return "extracted", candidates, None
    if mime.endswith("spreadsheetml.sheet"):
        try:
            _, candidates = parse_xlsx(content)
            return "extracted", candidates, None
        except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, ValueError) as error:
            return "failed", [], f"Spreadsheet could not be parsed: {error}"
    if mime == "application/pdf":
        text = extract_selectable_pdf_text(content)
        if not text.strip():
            return "needs_review", [], "No safely extractable text found. Use optional local Tesseract OCR or manual entry."
        return "extracted", extract_text_candidates(text), None
    if mime.startswith("image/"):
        return "needs_review", [], "Image accepted; optional local Tesseract OCR is not configured."
    return "failed", [], "Unsupported processor"

