"""Deterministic PDF/DOCX -> Markdown extraction.

This module deliberately does **not** call an LLM by default. The previous
implementation (``tools/sync_guidelines.py``) sent the whole source document to
DeepSeek and wrote back whatever came out, which made the normalised guideline
depend on a remote model, lose tables, and change even when the source had not
changed. Here extraction is local and stable: the same source bytes always
produce the same Markdown, which is what makes the "source hash -> output hash"
manifest trustworthy.

Table and heading structure is preserved, because label/schema rules in the
annotation guidelines live almost entirely in tables (point ids, sublabel
names, state conditions).

Optional LLM polishing stays available through ``--polish`` in
``tools/sync_all.py``; it refines wording of the extraction, it never invents
or drops structure.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

SUPPORTED_SUFFIXES = {".docx", ".pdf"}

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# --------------------------------------------------------------------------- #
# hashing
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceFile:
    path: Path
    rel: str
    suffix: str
    digest: str
    size: int


def discover_sources(source_dir: Path) -> list[SourceFile]:
    """Return supported source documents, ordered deterministically."""
    files = sorted(
        (p for p in source_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES),
        key=lambda p: p.relative_to(source_dir).as_posix().lower(),
    )
    return [
        SourceFile(
            path=p,
            rel=p.relative_to(source_dir).as_posix(),
            suffix=p.suffix.lower(),
            digest=sha256_file(p),
            size=p.stat().st_size,
        )
        for p in files
    ]


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #
def _docx_heading_level(style_id: str | None) -> int | None:
    """Map a Word paragraph style id to a Markdown heading level."""
    if not style_id:
        return None
    match = re.match(r"(?:Heading|heading)\s*(\d+)", style_id)
    if match:
        return max(1, min(6, int(match.group(1))))
    if style_id in {"Title", "title"}:
        return 1
    return None


def _para_text(paragraph: ET.Element) -> str:
    """Text of a ``w:p`` with tab and line-break preserved."""
    parts: list[str] = []
    for node in paragraph.iter():
        tag = node.tag
        if tag == f"{_W}t":
            parts.append(node.text or "")
        elif tag == f"{_W}tab":
            parts.append("\t")
        elif tag in (f"{_W}br", f"{_W}cr"):
            parts.append("\n")
    return "".join(parts)


def _para_style(paragraph: ET.Element) -> str | None:
    style = paragraph.find(f"{_W}pPr/{_W}pStyle")
    if style is None:
        return None
    return style.get(f"{_W}val")


def _is_list_item(paragraph: ET.Element) -> bool:
    return paragraph.find(f"{_W}pPr/{_W}numPr") is not None


def _cell_text(cell: ET.Element) -> str:
    chunks = [_para_text(p).strip() for p in cell.findall(f"{_W}p")]
    text = " ".join(chunk for chunk in chunks if chunk)
    # A literal pipe would break the Markdown table row.
    return re.sub(r"\s+", " ", text).replace("|", r"\|").strip()


def _table_to_markdown(table: ET.Element) -> str:
    rows: list[list[str]] = []
    for row in table.findall(f"{_W}tr"):
        cells = [_cell_text(cell) for cell in row.findall(f"{_W}tc")]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(out)


def extract_docx(path: Path) -> str:
    """Extract a .docx in document order, keeping headings, lists and tables."""
    with zipfile.ZipFile(path) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:  # pragma: no cover - corrupt file
            raise RuntimeError(f"{path.name}: not a Word document (no word/document.xml)") from exc

    root = ET.fromstring(document_xml)
    body = root.find(f"{_W}body")
    if body is None:  # pragma: no cover - corrupt file
        raise RuntimeError(f"{path.name}: empty document body")

    blocks: list[str] = []
    for child in body:
        if child.tag == f"{_W}p":
            text = _para_text(child).strip()
            if not text:
                continue
            level = _docx_heading_level(_para_style(child))
            if level:
                blocks.append("#" * level + " " + text)
            elif _is_list_item(child):
                blocks.append("- " + text)
            else:
                blocks.append(text)
        elif child.tag == f"{_W}tbl":
            markdown = _table_to_markdown(child)
            if markdown:
                blocks.append(markdown)

    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
# Several pure-Python/wheel PDF engines are common in the wild and any one of
# them is enough. Hard-requiring exactly one made the whole sync pipeline die on
# a machine that had the others installed (this host reaches no package index,
# so "just pip install pypdf" is not always an available answer). The order is
# fixed so the extraction stays deterministic for a given environment, and the
# chosen engine is reported by both extract_pdf and the generated file header.
PDF_BACKENDS: tuple[str, ...] = ("pypdf", "pdfplumber", "pypdfium2", "pdfminer")


def available_pdf_backends() -> list[str]:
    """Installed PDF engines, in the deterministic order they are tried."""
    found: list[str] = []
    for name in PDF_BACKENDS:
        if importlib.util.find_spec(name) is not None:
            found.append(name)
    return found


def pdf_backend() -> str:
    """Name of the engine extract_pdf will use, or "" when none is installed."""
    found = available_pdf_backends()
    return found[0] if found else ""


def _pdf_with_pypdf(path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - depends on the document
            raise RuntimeError(f"{path.name}: PDF is encrypted and cannot be read") from exc
    return [(page.extract_text() or "").strip() for page in reader.pages]


def _pdf_with_pdfplumber(path: Path) -> list[str]:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            pages.append((page.extract_text() or "").strip())
    return pages


def _pdf_with_pypdfium2(path: Path) -> list[str]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        pages: list[str] = []
        for index in range(len(document)):
            textpage = document[index].get_textpage()
            try:
                # Bounded extraction keeps the page box order, which is what the
                # guideline tables need; the plain variant scrambles columns.
                pages.append((textpage.get_text_bounded() or "").strip())
            finally:
                textpage.close()
        return pages
    finally:
        document.close()


def _pdf_with_pdfminer(path: Path) -> list[str]:
    from pdfminer.high_level import extract_text as pdfminer_extract

    # pdfminer has no per-page entry point that keeps running page numbers
    # cheaply, so split on the form feed it emits between pages.
    raw = pdfminer_extract(str(path)) or ""
    return [chunk.strip() for chunk in raw.split("\f")]


_PDF_READERS = {
    "pypdf": _pdf_with_pypdf,
    "pdfplumber": _pdf_with_pdfplumber,
    "pypdfium2": _pdf_with_pypdfium2,
    "pdfminer": _pdf_with_pdfminer,
}


def extract_pdf(path: Path, *, backend: str | None = None) -> str:
    """Extract a PDF page by page with the first installed engine.

    Page markers are kept so a reviewer can tell which page a label table came
    from. Raises RuntimeError naming the engines that were tried and failed,
    instead of a bare ImportError.
    """
    candidates = [backend] if backend else available_pdf_backends()
    if not candidates:
        raise RuntimeError(
            f"{path.name}: no PDF engine installed; install one of "
            f"{', '.join(PDF_BACKENDS)} (`pip install -r requirements.txt`)"
        )

    failures: list[str] = []
    for name in candidates:
        reader = _PDF_READERS[name]
        try:
            payload = reader(path)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        pages = [
            f"<!-- page {number} -->\n\n{text}"
            for number, text in enumerate(payload, start=1)
            if text
        ]
        if pages:
            return "\n\n".join(pages)
        failures.append(f"{name}: extracted no text (scanned image without OCR?)")

    raise RuntimeError(
        f"{path.name}: every PDF engine failed -> " + "; ".join(failures)
    )


def extract_text(source: SourceFile) -> str:
    text = extract_docx(source.path) if source.suffix == ".docx" else extract_pdf(source.path)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------------------- #
# normalisation into one guideline document
# --------------------------------------------------------------------------- #
def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "document"


def extraction_engine(source: SourceFile) -> str:
    """Human-readable engine name for a source, recorded in generated output."""
    return "python-docx" if source.suffix == ".docx" else (pdf_backend() or "unknown")


def build_guideline_markdown(sources: list[SourceFile], bodies: dict[str, str]) -> str:
    """Compose the normalised guideline with a generated-file header."""
    header = [
        "<!-- GENERATED FILE - do not edit by hand.",
        "     Produced by `python tools/sync_all.py` from the original documents in",
        "     `guildlline/`. Edit the source documents and re-run the command; this",
        "     file is overwritten. -->",
        "",
        "# Guideline tổng hợp (sinh tự động)",
        "",
        f"Engine trích xuất PDF: `{pdf_backend() or 'không có'}` (thứ tự ưu tiên: "
        + ", ".join(PDF_BACKENDS)
        + ").",
        "",
        "Nguồn gốc:",
        "",
    ]
    for source in sources:
        header.append(f"- `guildlline/{source.rel}` (sha256 `{source.digest[:12]}`, {source.size} bytes)")
    header.append("")

    sections = ["\n".join(header)]
    for source in sources:
        body = bodies[source.rel]
        sections.append(f"## Nguồn: `{source.rel}`\n\n{body}")
    return "\n\n---\n\n".join(sections).rstrip() + "\n"
