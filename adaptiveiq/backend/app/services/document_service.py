"""Secure study-material extraction, normalization, section-aware chunking, and ephemeral staging.

Supports PDF, DOCX, and TXT uploads up to `max_document_bytes` (10 MB by default):
- Validates filename extension, actual file signature / container structure, and zip decompression bounds.
- Never executes macros, embedded objects, scripts, or external XML entities (`defusedxml` + XML-only read).
- Keeps no permanent uploaded files on disk: raw upload bytes are discarded immediately after extraction, and
  only normalized sections/chunks live briefly in a user-scoped TTL store until generation starts.
- Detects scanned / image-only PDFs without selectable text and reports explicitly that OCR is not supported.
"""
from __future__ import annotations

import io
import math
import re
import secrets
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from defusedxml import ElementTree as SafeET
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MACRO_EXTENSIONS = {".doc", ".docm", ".dot", ".dotm", ".xlsm", ".pptm"}
MAX_ZIP_ENTRIES = 1000
MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
MIN_PDF_SELECTABLE_WORDS = 15
TARGET_CHUNK_WORDS = 165
MAX_CHUNK_WORDS = 240
MAX_HEADINGS = 50
MAX_STORED_PER_USER = 10

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_KNOWN_BINARY_PREFIXES = (
    b"MZ",
    b"\x7fELF",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"%PDF-",
    b"PK\x03\x04",
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # OLE compound file (.doc / .xls / .ppt)
)

_STOP = set("""a an the of to in on for and or is are was were be been being by with as at from that this these
those which what when where who whom whose why how it its into than then there their they them can could may
might will would shall should do does did not no yes if else so such any all each other some most more less
one two three four chapter section unit page figure table example introduction summary overview""".split())


class DocumentError(Exception):
    """Safe, user-readable upload or extraction error."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class DocumentSection:
    text: str
    heading: str | None = None
    section: str | None = None
    page: int | None = None
    page_end: int | None = None


@dataclass
class DocumentChunk:
    chunk_index: int
    text: str
    document_name: str
    file_type: Literal["pdf", "docx", "txt"]
    page: int | None = None
    page_end: int | None = None
    section: str | None = None
    heading: str | None = None
    word_count: int = 0

    def to_meta(self) -> dict:
        out = {
            "document_name": self.document_name,
            "file_type": self.file_type,
            "chunk_index": self.chunk_index,
        }
        if self.page is not None:
            out["page"] = self.page
        if self.page_end is not None and self.page_end != self.page:
            out["page_end"] = self.page_end
        if self.section:
            out["section"] = self.section
        if self.heading:
            out["heading"] = self.heading
        return out

    def to_param_dict(self) -> dict:
        return {"text": self.text, **self.to_meta()}


@dataclass
class ExtractedDocument:
    document_name: str
    file_type: Literal["pdf", "docx", "txt"]
    size_bytes: int
    page_count: int | None
    word_count: int
    sections: list[DocumentSection]
    headings: list[str]
    chunks: list[DocumentChunk]
    recommended_max_questions: int
    warning: str | None = None
    preview: str = ""


@dataclass
class ChunkSelection:
    chunks: list[DocumentChunk]
    requested_count: int
    supported_count: int
    effective_count: int
    insufficient_content_note: str | None = None
    warning: str | None = None


def sanitize_filename(raw: str | None) -> str:
    base = Path(str(raw or "document")).name
    cleaned = re.sub(r"[\x00-\x1f\x7f<>:\"/\\|?*]+", "_", base).strip(" .")
    return (cleaned or "document")[:160]


def normalize_text(raw: str) -> str:
    if not raw:
        return ""
    txt = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Remove soft hyphens / zero-width marks and rejoin words hyphenated across line breaks.
    txt = re.sub(r"[\u00ad\u200b-\u200f\ufeff]", "", txt)
    txt = re.sub(r"(?<=[A-Za-z])-\n(?=[A-Za-z])", "", txt)
    # Remove other ASCII control chars except newline and tab.
    txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", txt)
    lines = []
    blank_run = 0
    for line in txt.split("\n"):
        collapsed = " ".join(line.split())
        if not collapsed:
            blank_run += 1
            if blank_run == 1 and lines:
                lines.append("")
        else:
            blank_run = 0
            lines.append(collapsed)
    return "\n".join(lines).strip()


def _split_sentences(text: str) -> list[str]:
    flat = " ".join(text.split())
    if not flat:
        return []
    parts = re.split(r"(?<=[.!?])\s+", flat)
    return [p.strip() for p in parts if p.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", text))


def _looks_like_heading(line: str, prev_blank: bool = True, next_blank: bool = False) -> str | None:
    s = line.strip()
    if not s or len(s) < 3 or len(s) > 100:
        return None
    # Strip trailing page numbers like "Paging 12" in TOC lines? Keep natural headings only.
    md = re.match(r"^#{1,6}\s+(.+)$", s)
    if md:
        return md.group(1).strip()[:120]
    if s.endswith((".", "?", "!", ";", ",")) and not re.match(r"^(?:chapter|unit|section)\s+\d", s, re.I):
        return None
    if re.match(r"^(?:chapter|unit|module|part|section)\s+\d+(?:\.\d+)*\b", s, re.I):
        return s[:120]
    if re.match(r"^\d+(?:\.\d+){0,3}[\).:\s]+[A-Z][A-Za-z0-9 ,\-/&()]{2,80}$", s) and len(s.split()) <= 12:
        return s[:120]
    words = s.split()
    if 1 <= len(words) <= 9 and s.isupper() and any(c.isalpha() for c in s):
        return s.title()[:120]
    if (prev_blank or next_blank) and 2 <= len(words) <= 9 and ":" not in s:
        cap_words = sum(1 for w in words if w[:1].isupper() or w.lower() in _STOP)
        if cap_words == len(words) and not any(ch.isdigit() for ch in s[-3:]):
            return s[:120]
    return None


def _detect_type_and_validate(filename: str | None, content_type: str | None, data: bytes, max_bytes: int) -> Literal["pdf", "docx", "txt"]:
    if not data:
        raise DocumentError(422, "The uploaded file is empty.")
    if len(data) > max_bytes:
        mb = max(1, max_bytes // (1024 * 1024))
        raise DocumentError(413, f"File is too large. Maximum allowed size is {mb} MB.")
    name = sanitize_filename(filename)
    ext = Path(name).suffix.lower()
    if ext in MACRO_EXTENSIONS:
        raise DocumentError(415, "Legacy or macro-enabled office formats (.doc, .docm) are not supported. Upload a PDF, DOCX, or TXT file.")
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentError(415, "Unsupported file format. Only PDF, DOCX, and TXT files are supported.")
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if "macroenabled" in ctype:
        raise DocumentError(415, "Macro-enabled documents are not allowed. Upload a PDF, DOCX, or TXT file.")

    head = data[:1024]
    if ext == ".pdf":
        if b"%PDF-" not in head:
            raise DocumentError(422, "This file does not look like a valid PDF document.")
        return "pdf"

    if ext == ".docx":
        if not (data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06")):
            raise DocumentError(422, "This file does not look like a valid DOCX archive.")
        return "docx"

    # .txt validation: block obvious binary headers or unexpected NUL bytes
    if any(data.startswith(sig) for sig in _KNOWN_BINARY_PREFIXES):
        raise DocumentError(422, "File content does not match a plain text (.txt) document.")
    if not (data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff")) and b"\x00" in data[:8192]:
        raise DocumentError(422, "This .txt file contains binary data rather than readable text.")
    return "txt"


def _flatten_pdf_outline(outline, reader: PdfReader, page_map: dict[int, str], depth: int = 0):
    if depth > 6 or not outline:
        return
    for item in outline:
        if isinstance(item, list):
            _flatten_pdf_outline(item, reader, page_map, depth + 1)
            continue
        title = getattr(item, "title", None)
        if not title and isinstance(item, dict):
            title = item.get("/Title")
        if title:
            try:
                pno = reader.get_destination_page_number(item)
                if pno is not None and (pno + 1) not in page_map:
                    clean = " ".join(str(title).split())[:120]
                    if clean:
                        page_map[pno + 1] = clean
            except Exception:
                continue


def _extract_pdf(data: bytes) -> tuple[list[DocumentSection], int, str | None]:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except (PdfReadError, Exception) as exc:
        raise DocumentError(422, "Could not open this PDF. The file may be corrupted or damaged.") from exc

    if reader.is_encrypted:
        raise DocumentError(422, "This PDF is password-protected and cannot be read without decrypting it first.")

    try:
        num_pages = len(reader.pages)
    except (PdfReadError, Exception) as exc:
        raise DocumentError(422, "Could not inspect pages in this PDF. The file may be corrupted.") from exc

    if num_pages == 0:
        raise DocumentError(422, "This PDF has no pages.")

    bookmark_titles: dict[int, str] = {}
    try:
        _flatten_pdf_outline(reader.outline, reader, bookmark_titles)
    except Exception:
        bookmark_titles = {}

    sections: list[DocumentSection] = []
    total_selectable_words = 0
    total_images = 0
    current_heading: str | None = None

    for page_no in range(1, num_pages + 1):
        try:
            page = reader.pages[page_no - 1]
            raw_page = page.extract_text() or ""
        except (PdfReadError, Exception):
            raw_page = ""

        try:
            total_images += len(getattr(page, "images", []) or [])
        except Exception:
            pass

        norm_page = normalize_text(raw_page)
        page_words = _word_count(norm_page)
        total_selectable_words += page_words

        if page_no in bookmark_titles:
            current_heading = bookmark_titles[page_no]

        if not norm_page:
            continue

        lines = norm_page.split("\n")
        buf: list[str] = []
        active_heading = current_heading

        def _flush_buf():
            nonlocal buf
            text = "\n".join(buf).strip()
            if text:
                sections.append(DocumentSection(
                    text=text,
                    heading=active_heading,
                    section=active_heading or f"Page {page_no}",
                    page=page_no,
                    page_end=page_no,
                ))
            buf = []

        for idx, line in enumerate(lines):
            prev_blank = idx == 0 or not lines[idx - 1].strip()
            next_blank = idx + 1 < len(lines) and not lines[idx + 1].strip()
            h = _looks_like_heading(line, prev_blank=prev_blank, next_blank=next_blank)
            if h:
                _flush_buf()
                active_heading = h
                current_heading = h
            else:
                if line.strip():
                    buf.append(line.strip())
        _flush_buf()

    if total_selectable_words < MIN_PDF_SELECTABLE_WORDS:
        if total_images > 0 or total_selectable_words == 0:
            raise DocumentError(
                422,
                "This PDF does not contain selectable text (it appears to be scanned images). "
                "OCR is not supported; please upload a text-based PDF, DOCX, or TXT file.",
            )
        raise DocumentError(
            422,
            f"This PDF contains almost no extractable text ({total_selectable_words} words found). "
            "Scanned documents without selectable text require OCR, which is not supported.",
        )

    if not sections:
        raise DocumentError(422, "No readable text could be extracted from this PDF.")

    warning = None
    if total_images >= max(2, num_pages) and total_selectable_words < num_pages * 35:
        warning = "Some pages in this PDF appear image-heavy; only selectable text was extracted (OCR is not supported)."
    return sections, num_pages, warning


def _docx_paragraph_text(p_elem) -> str:
    chunks: list[str] = []
    for node in p_elem.iter():
        if node.tag == f"{_W_NS}t" and node.text:
            chunks.append(node.text)
        elif node.tag == f"{_W_NS}tab":
            chunks.append(" ")
        elif node.tag == f"{_W_NS}br" and node.get(f"{_W_NS}type") != "page":
            chunks.append("\n")
    return " ".join("".join(chunks).split())


def _docx_paragraph_style(p_elem) -> str:
    ppr = p_elem.find(f"{_W_NS}pPr")
    if ppr is None:
        return ""
    pstyle = ppr.find(f"{_W_NS}pStyle")
    if pstyle is None:
        return ""
    return (pstyle.get(f"{_W_NS}val") or "").strip()


def _docx_has_page_break(p_elem) -> bool:
    for node in p_elem.iter():
        if node.tag == f"{_W_NS}lastRenderedPageBreak":
            return True
        if node.tag == f"{_W_NS}br" and node.get(f"{_W_NS}type") == "page":
            return True
    return False


def _extract_docx(data: bytes) -> tuple[list[DocumentSection], int | None, str | None]:
    try:
        zf_ctx = zipfile.ZipFile(io.BytesIO(data), "r")
    except (zipfile.BadZipFile, Exception) as exc:
        raise DocumentError(422, "Could not open this DOCX file. The file appears corrupted.") from exc

    with zf_ctx as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise DocumentError(422, "This DOCX archive exceeds the maximum allowed entry limit.")
        if sum(max(0, i.file_size) for i in infos) > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise DocumentError(422, "This DOCX archive exceeds the safe uncompressed size limit.")
        names = [i.filename.replace("\\", "/") for i in infos]
        lower_names = [n.lower() for n in names]
        if any("vbaproject" in n or "vbadata" in n or (n.endswith(".bin") and "vba" in n) for n in lower_names):
            raise DocumentError(422, "Documents containing macros or executable content are not supported.")
        if "word/document.xml" not in names:
            raise DocumentError(422, "This DOCX file is corrupted or missing document content.")

        # Read with a hard byte ceiling regardless of central directory headers.
        with zf.open("word/document.xml") as f:
            xml_bytes = f.read(MAX_DOCX_XML_BYTES + 1)
        if len(xml_bytes) > MAX_DOCX_XML_BYTES:
            raise DocumentError(422, "This DOCX document XML exceeds the safe size limit.")

    try:
        root = SafeET.fromstring(xml_bytes)
    except Exception as exc:
        raise DocumentError(422, "Could not parse the XML content of this DOCX file.") from exc

    body = root.find(f"{_W_NS}body")
    if body is None:
        raise DocumentError(422, "This DOCX file contains no document body.")

    sections: list[DocumentSection] = []
    current_heading: str | None = None
    cur_page = 1
    buf: list[str] = []
    buf_page_start = 1

    def _flush(page_end: int):
        nonlocal buf, buf_page_start
        txt = normalize_text("\n".join(buf))
        if txt:
            sections.append(DocumentSection(
                text=txt,
                heading=current_heading,
                section=current_heading or f"Section {len(sections) + 1}",
                page=buf_page_start,
                page_end=page_end,
            ))
        buf = []
        buf_page_start = page_end

    for child in list(body):
        if child.tag == f"{_W_NS}p":
            if _docx_has_page_break(child) and buf:
                cur_page += 1
            style = _docx_paragraph_style(child)
            txt = _docx_paragraph_text(child)
            if not txt:
                continue
            is_heading_style = bool(re.match(r"^(?:Heading\s*[1-6]|Title|Subtitle)$", style, re.I))
            inferred = _looks_like_heading(txt, prev_blank=True, next_blank=True)
            if is_heading_style or (inferred and len(txt.split()) <= 10 and not txt.endswith(".")):
                _flush(cur_page)
                current_heading = txt[:120]
                buf_page_start = cur_page
            else:
                if not buf:
                    buf_page_start = cur_page
                buf.append(txt)
        elif child.tag == f"{_W_NS}tbl":
            row_texts = []
            for tr in child.findall(f".//{_W_NS}tr"):
                cells = []
                for tc in tr.findall(f"./{_W_NS}tc"):
                    cell_parts = [_docx_paragraph_text(p) for p in tc.findall(f".//{_W_NS}p")]
                    joined = " ".join(x for x in cell_parts if x)
                    if joined:
                        cells.append(joined)
                if cells:
                    row_texts.append(" | ".join(cells))
            if row_texts:
                if not buf:
                    buf_page_start = cur_page
                buf.extend(row_texts)

    _flush(cur_page)
    if not sections:
        raise DocumentError(422, "This DOCX file contains no readable text.")
    return sections, (cur_page if cur_page > 1 else None), None


def _decode_text_bytes(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise DocumentError(422, "Could not decode this UTF-16 text file.") from exc
    else:
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise DocumentError(422, "Could not decode this text file as readable text.")

    sample = text[:8192]
    if sample:
        bad = sum(1 for ch in sample if (ord(ch) < 32 and ch not in "\n\r\t"))
        if bad / len(sample) > 0.02:
            raise DocumentError(422, "This file contains unreadable control characters instead of plain text.")
    return text


def _extract_txt(data: bytes) -> tuple[list[DocumentSection], int | None, str | None]:
    raw = _decode_text_bytes(data)
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = raw.split("\n")
    sections: list[DocumentSection] = []
    current_heading: str | None = None
    buf: list[str] = []

    def _flush():
        nonlocal buf
        txt = normalize_text("\n".join(buf))
        if txt:
            sections.append(DocumentSection(
                text=txt,
                heading=current_heading,
                section=current_heading or f"Section {len(sections) + 1}",
                page=None,
                page_end=None,
            ))
        buf = []

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].strip()
        next_line = raw_lines[i + 1].strip() if i + 1 < len(raw_lines) else ""
        # Underlined Markdown/RST heading: Title followed by === or ---
        if line and len(line) <= 120 and next_line and re.fullmatch(r"[=\-]{3,}", next_line):
            _flush()
            current_heading = line[:120]
            i += 2
            continue
        prev_blank = i == 0 or not raw_lines[i - 1].strip()
        next_blank = i + 1 < len(raw_lines) and not next_line
        h = _looks_like_heading(line, prev_blank=prev_blank, next_blank=next_blank)
        if h:
            _flush()
            current_heading = h
            i += 1
            continue
        if line:
            buf.append(line)
        else:
            buf.append("")
        i += 1

    _flush()
    if not sections:
        raise DocumentError(422, "The uploaded text file is empty.")
    return sections, None, None


def _build_chunks(
    sections: list[DocumentSection],
    document_name: str,
    file_type: Literal["pdf", "docx", "txt"],
    target_words: int = TARGET_CHUNK_WORDS,
    max_words: int = MAX_CHUNK_WORDS,
) -> list[DocumentChunk]:
    """Splits normalized sections into ~140-220 word chunks while preserving headings and page numbers."""
    chunks: list[DocumentChunk] = []

    # Group tiny consecutive sections with identical heading/section when appropriate,
    # while keeping clear page & heading attribution on each chunk.
    cur_parts: list[str] = []
    cur_words = 0
    cur_heading: str | None = None
    cur_section: str | None = None
    cur_page_start: int | None = None
    cur_page_end: int | None = None

    def _emit():
        nonlocal cur_parts, cur_words, cur_heading, cur_section, cur_page_start, cur_page_end
        text = " ".join(cur_parts).strip()
        wc = _word_count(text)
        if text and wc > 0:
            chunks.append(DocumentChunk(
                chunk_index=len(chunks),
                text=text,
                document_name=document_name,
                file_type=file_type,
                page=cur_page_start,
                page_end=cur_page_end,
                section=cur_section,
                heading=cur_heading,
                word_count=wc,
            ))
        cur_parts = []
        cur_words = 0

    for sec in sections:
        sec_sentences = _split_sentences(sec.text)
        if not sec_sentences:
            continue
        sec_heading = sec.heading or cur_heading
        sec_label = sec.section or sec_heading
        # Start a new chunk whenever a new explicit heading arrives so section/chapter filters stay exact.
        if cur_words > 0 and sec.heading and cur_heading and sec.heading != cur_heading:
            _emit()

        for sent in sec_sentences:
            sw = len(sent.split())
            if cur_parts and cur_words + sw > max_words and cur_words >= 70:
                _emit()
            if not cur_parts:
                cur_heading = sec_heading
                cur_section = sec_label
                cur_page_start = sec.page
                cur_page_end = sec.page_end if sec.page_end is not None else sec.page
            else:
                if cur_heading is None:
                    cur_heading = sec_heading
                if cur_section is None:
                    cur_section = sec_label
                if sec.page is not None:
                    if cur_page_start is None:
                        cur_page_start = sec.page
                    cur_page_end = sec.page_end if sec.page_end is not None else sec.page
            cur_parts.append(sent)
            cur_words += sw
            if cur_words >= target_words:
                _emit()

    _emit()
    # Merge tiny final tail chunk into previous chunk if same heading/section
    if len(chunks) >= 2 and chunks[-1].word_count < 45 and chunks[-1].heading == chunks[-2].heading:
        last = chunks.pop()
        prev = chunks[-1]
        prev.text = f"{prev.text} {last.text}".strip()
        prev.word_count = _word_count(prev.text)
        if last.page_end is not None:
            prev.page_end = last.page_end
        elif last.page is not None:
            prev.page_end = last.page
    return chunks


def extract_document(
    filename: str | None,
    content_type: str | None,
    data: bytes,
    max_bytes: int = 10 * 1024 * 1024,
    min_words_per_q: int = 22,
    min_doc_words: int = 40,
) -> ExtractedDocument:
    ftype = _detect_type_and_validate(filename, content_type, data, max_bytes)
    doc_name = sanitize_filename(filename)

    if ftype == "pdf":
        sections, page_count, warning = _extract_pdf(data)
    elif ftype == "docx":
        sections, page_count, warning = _extract_docx(data)
    else:
        sections, page_count, warning = _extract_txt(data)

    chunks = _build_chunks(sections, doc_name, ftype)
    total_words = sum(_word_count(s.text) for s in sections)
    if total_words == 0 or not chunks:
        raise DocumentError(422, f"'{doc_name}' did not contain any extractable words.")

    headings: list[str] = []
    seen_h: set[str] = set()
    for s in sections:
        h = (s.heading or "").strip()
        if h and h.lower() not in seen_h:
            seen_h.add(h.lower())
            headings.append(h)
            if len(headings) >= MAX_HEADINGS:
                break

    total_sentences = sum(max(1, len(_split_sentences(c.text))) for c in chunks)
    if total_words < min_doc_words:
        rec_max = 0
        if not warning:
            warning = (f"This document only has {total_words} words (at least {min_doc_words} words are needed "
                       "for grounded MCQ generation).")
    else:
        rec_max = min(30, max(1, min(total_sentences * 2, total_words // max(1, min_words_per_q))))

    preview = " ".join(sections[0].text.split())[:260]
    return ExtractedDocument(
        document_name=doc_name,
        file_type=ftype,
        size_bytes=len(data),
        page_count=page_count,
        word_count=total_words,
        sections=sections,
        headings=headings,
        chunks=chunks,
        recommended_max_questions=rec_max,
        warning=warning,
        preview=preview,
    )


def _query_terms(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z][a-z0-9]+|\d+(?:\.\d+)?", (text or "").lower())
        if w not in _STOP and (len(w) > 2 or w.isdigit())
    }


def _difficulty_bonus(chunk_text: str, heading: str | None, difficulty: str) -> float:
    wc = _word_count(chunk_text)
    lower = chunk_text.lower()
    if difficulty == "hard":
        cues = len(re.findall(r"\b(?:however|whereas|although|unlike|because|therefore|complexity|trade-off|compare|equation|formula|prove|derive)\b", lower))
        nums = len(re.findall(r"\b\d+(?:\.\d+)?\b", chunk_text))
        return min(0.35, 0.05 * cues + 0.03 * nums + (0.08 if wc >= 130 else 0.0))
    if difficulty == "easy":
        cues = len(re.findall(r"\b(?:is defined as|refers to|means|known as|consists of|is called|basic|fundamental)\b", lower))
        return min(0.35, 0.08 * cues + (0.06 if heading else 0.0))
    return 0.0


def select_chunks(
    doc: ExtractedDocument,
    question_count: int,
    topic: str | None = None,
    subject: str | None = None,
    objectives: list[str] | None = None,
    section_filter: str | None = None,
    difficulty: str = "mixed",
    min_words: int = 40,
    min_words_per_q: int = 22,
) -> ChunkSelection:
    """Filters and ranks document chunks by topic/section relevance, difficulty, and spread across sections."""
    pool = list(doc.chunks)
    if section_filter and section_filter.strip():
        needle = " ".join(section_filter.lower().split())
        filtered = [
            c for c in pool
            if (c.heading and needle in c.heading.lower()) or (c.section and needle in c.section.lower())
        ]
        if not filtered:
            raise DocumentError(
                422,
                f"No readable content matched section '{section_filter.strip()}' in '{doc.document_name}'.",
            )
        pool = filtered

    usable_words = sum(c.word_count for c in pool)
    if usable_words < min_words:
        scope = f"section '{section_filter.strip()}' of " if section_filter and section_filter.strip() else ""
        raise DocumentError(
            422,
            f"Insufficient content in {scope}'{doc.document_name}' ({usable_words} words found; at least {min_words} words are needed to generate grounded questions).",
        )

    sentence_count = sum(max(1, len(_split_sentences(c.text))) for c in pool)
    max_supported = max(1, min(sentence_count * 2, usable_words // max(1, min_words_per_q)))
    effective_count = min(question_count, max_supported)
    insufficient_note = None
    if effective_count < question_count:
        insufficient_note = (
            f"Insufficient document material for {question_count} questions: generated target adjusted to "
            f"{effective_count} based on the {usable_words} words extracted."
        )

    query_parts = [p for p in [section_filter, topic, *(objectives or [])] if p and str(p).strip()]
    primary_query = " ".join(query_parts).strip()
    secondary_query = " ".join(p for p in [primary_query, subject] if p and str(p).strip()).strip()
    q_terms = _query_terms(primary_query) or _query_terms(secondary_query)

    tfidf_scores = [0.0] * len(pool)
    if primary_query and len(pool) > 1:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            docs_text = [primary_query] + [f"{c.heading or ''} {c.section or ''} {c.text}" for c in pool]
            m = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform(docs_text)
            tfidf_scores = [float(x) for x in cosine_similarity(m[0:1], m[1:]).ravel()]
        except Exception:
            tfidf_scores = [0.0] * len(pool)

    scored: list[tuple[float, DocumentChunk]] = []
    for idx, ch in enumerate(pool):
        overlap = 0.0
        if q_terms:
            c_terms = _query_terms(f"{ch.heading or ''} {ch.section or ''} {ch.text}")
            overlap = len(q_terms & c_terms) / len(q_terms)
            h_terms = _query_terms(f"{ch.heading or ''} {ch.section or ''}")
            heading_hit = 0.25 if (q_terms & h_terms) else 0.0
        else:
            heading_hit = 0.0
        size_bonus = min(0.15, ch.word_count / 1200.0)
        diff_bonus = _difficulty_bonus(ch.text, ch.heading, difficulty)
        score = tfidf_scores[idx] * 1.4 + overlap + heading_hit + size_bonus + diff_bonus
        scored.append((score, ch))

    desired = min(len(pool), max(effective_count * 2, min(12, len(pool))), 40)

    # Encourage breadth across headings/sections/pages before repeating a section.
    if q_terms and any(s > 0.2 for s, _ in scored):
        ranked = [ch for _, ch in sorted(scored, key=lambda pair: (-pair[0], pair[1].chunk_index))]
        selected: list[DocumentChunk] = []
        seen_ids: set[int] = set()
        seen_buckets: set[str] = set()
        for ch in ranked:
            bucket = (ch.heading or ch.section or f"p:{ch.page or ch.chunk_index}").lower()
            if bucket not in seen_buckets:
                seen_buckets.add(bucket)
                seen_ids.add(ch.chunk_index)
                selected.append(ch)
                if len(selected) >= desired:
                    break
        for ch in ranked:
            if len(selected) >= desired:
                break
            if ch.chunk_index not in seen_ids:
                seen_ids.add(ch.chunk_index)
                selected.append(ch)
    else:
        # Broad/unspecified topic: sample evenly across the entire document so long docs aren't front-biased.
        if len(pool) <= desired:
            selected = list(pool)
        else:
            step = len(pool) / desired
            idxs = []
            seen_i: set[int] = set()
            for k in range(desired):
                pos = min(len(pool) - 1, math.floor(k * step))
                while pos in seen_i and pos + 1 < len(pool):
                    pos += 1
                seen_i.add(pos)
                idxs.append(pos)
            selected = [pool[i] for i in idxs]

    warn = doc.warning
    if q_terms and not any((_query_terms(f"{c.heading or ''} {c.section or ''} {c.text}") & q_terms) for c in selected):
        msg = f"No exact keyword matches for '{topic}' were found; questions remain strictly grounded in the uploaded file."
        warn = f"{warn} {msg}".strip() if warn else msg

    return ChunkSelection(
        chunks=selected,
        requested_count=question_count,
        supported_count=max_supported,
        effective_count=effective_count,
        insufficient_content_note=insufficient_note,
        warning=warn,
    )


@dataclass
class _StoredEntry:
    user_id: int
    created_at: float
    doc: ExtractedDocument


class DocumentStore:
    """User-scoped ephemeral in-memory store for normalized extracted study material (no permanent files)."""

    def __init__(self, ttl_seconds: int = 1800, max_per_user: int = MAX_STORED_PER_USER):
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.max_per_user = max(1, int(max_per_user))
        self._items: dict[str, _StoredEntry] = {}
        self._lock = threading.Lock()

    def _purge_expired_locked(self, now: float):
        cutoff = now - self.ttl_seconds
        expired = [k for k, v in self._items.items() if v.created_at < cutoff]
        for k in expired:
            del self._items[k]

    def put(self, user_id: int, doc: ExtractedDocument) -> str:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_locked(now)
            user_keys = [(v.created_at, k) for k, v in self._items.items() if v.user_id == user_id]
            if len(user_keys) >= self.max_per_user:
                user_keys.sort()
                for _, old_key in user_keys[: len(user_keys) - self.max_per_user + 1]:
                    self._items.pop(old_key, None)
            token = secrets.token_urlsafe(24)
            self._items[token] = _StoredEntry(user_id=user_id, created_at=now, doc=doc)
            return token

    def get(self, doc_id: str, user_id: int) -> ExtractedDocument | None:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_locked(now)
            entry = self._items.get(doc_id)
            if entry is None or entry.user_id != user_id:
                return None
            return entry.doc

    def pop(self, doc_id: str, user_id: int) -> ExtractedDocument | None:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_locked(now)
            entry = self._items.get(doc_id)
            if entry is None or entry.user_id != user_id:
                return None
            del self._items[doc_id]
            return entry.doc

    def delete(self, doc_id: str, user_id: int) -> bool:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_locked(now)
            entry = self._items.get(doc_id)
            if entry is None or entry.user_id != user_id:
                return False
            del self._items[doc_id]
            return True

    def count(self) -> int:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_locked(now)
            return len(self._items)
