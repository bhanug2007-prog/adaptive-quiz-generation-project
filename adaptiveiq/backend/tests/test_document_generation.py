"""Document-based & topic-based MCQ generation tests (using disposable files & temp DB)."""
import io
import os
import textwrap
import zipfile

import docx
import pytest

from app.core.config import Settings
from app.models import AgentRun
from app.services.document_service import extract_document, select_chunks
from app.services.model_service import ModelService
from app.services.quality_service import QualityEvaluator
from app.services.validation_service import Validator, verify_source_grounding
from tests import fake_grok_server, fake_model_server
from tests.conftest import INVITE, _free_port, register, wait_run


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str], *, image_only: bool = False) -> bytes:
    """Builds a minimal valid spec-compliant PDF with selectable text or image XObjects."""
    objs: list[bytes] = []
    # 1: Catalog, 2: Pages, then 3: Font (if text) or 3: Image XObject (if image_only)
    page_ids = []
    if image_only:
        objs.append(b"")  # placeholder 1
        objs.append(b"")  # placeholder 2
        objs.append(b"<< /Type /XObject /Subtype /Image /Width 10 /Height 10 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 4 >>\nstream\n\x00\xff\x00\xff\nendstream")
        for _ in pages or [""]:
            c_id = len(objs) + 1
            objs.append(b"<< /Length 14 >>\nstream\nq /Im1 Do Q\nendstream")
            p_id = len(objs) + 1
            page_ids.append(p_id)
            objs.append(
                f"<< /Type /Page /Parent 2 0 R /Resources << /XObject << /Im1 3 0 R >> >> /MediaBox [0 0 612 792] /Contents {c_id} 0 R >>".encode()
            )
    else:
        objs.append(b"")  # 1: Catalog
        objs.append(b"")  # 2: Pages
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")  # 3: Font
        for page_text in pages:
            wrapped: list[str] = []
            for raw_ln in page_text.splitlines():
                if raw_ln.strip():
                    wrapped.extend(textwrap.wrap(raw_ln.strip(), width=78) or [" "])
            wrapped = wrapped or [" "]
            ops = ["BT", "/F1 11 Tf", "40 760 Td", "13 TL"]
            for idx, ln in enumerate(wrapped):
                prefix = "" if idx == 0 else "T* "
                ops.append(f"{prefix}({_pdf_escape(ln)}) Tj")
            ops.append("ET")
            stream = "\n".join(ops).encode("latin-1", errors="replace")
            c_id = len(objs) + 1
            objs.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
            p_id = len(objs) + 1
            page_ids.append(p_id)
            objs.append(
                f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> /MediaBox [0 0 612 792] /Contents {c_id} 0 R >>".encode()
            )

    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objs[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode())
    return bytes(out)


def make_docx(sections: list[tuple[str, list[str]]], *, table_rows: list[tuple[str, str]] | None = None) -> bytes:
    d = docx.Document()
    for heading, paras in sections:
        if heading:
            d.add_heading(heading, level=1)
        for p in paras:
            d.add_paragraph(p)
    if table_rows:
        t = d.add_table(rows=len(table_rows), cols=2)
        for i, (c0, c1) in enumerate(table_rows):
            t.cell(i, 0).text = c0
            t.cell(i, 1).text = c1
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


SCHEDULING_DOC = (
    "# Unit 1: CPU Scheduling Algorithms\n"
    "CPU scheduling algorithms decide which ready process runs next on a processor core. "
    "Round robin scheduling assigns a fixed time quantum to every runnable process so time-sharing systems keep interactive response times predictable. "
    "When the time quantum becomes very small, context switch cost dominates CPU overhead; when a larger time quantum is used, round robin behaves like first-come first-served. "
    "Shortest job first minimises average waiting time, while non-preemptive schedulers hold the CPU until the burst completes.\n\n"
    "# Unit 2: Starvation, Priority and Aging\n"
    "Priority scheduling and shortest job first can starve long jobs or low-priority tasks if short high-priority bursts keep arriving. "
    "Aging prevents starvation by gradually increasing the priority of waiting processes over time. "
    "Multilevel feedback queues move processes between queues based on observed burst length and interactive I/O behaviour, helping avoid needing the burst length in advance.\n"
)

BIO_DOC = (
    "# Cellular Genetics\n"
    "Deoxyribonucleic acid stores hereditary genetic instructions inside eukaryotic nuclei using four nucleotide bases: adenine, thymine, cytosine, and guanine. "
    "During transcription, RNA polymerase synthesises messenger RNA molecules from a complementary template strand. "
    "Ribosomes later translate codons into polypeptide chains during protein synthesis in the cytoplasm.\n"
)


@pytest.fixture(scope="session")
def grok_port():
    port = _free_port()
    srv = fake_grok_server.start(port)
    yield port
    srv.shutdown()


@pytest.fixture
def settings(tmp_path, model_port, grok_port):
    fake_grok_server.reset("pass")
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    return Settings(
        _env_file=None,
        environment="test",
        database_url=url,
        model_base_url=f"http://127.0.0.1:{model_port}",
        lecturer_invite_code=INVITE,
        secret_key="test-secret-" + "x" * 40,
        math_check=True,
        require_email_verification=False,
        grok_api_key="xai-test-doc-key-000",
        grok_base_url=f"http://127.0.0.1:{grok_port}",
        grok_model="grok-test",
        grok_timeout_s=1.0,
        grok_cooldown_s=300,
    )


def _upload(client, filename: str, data: bytes, content_type: str = "application/octet-stream"):
    return client.post("/api/documents/extract", files={"file": (filename, data, content_type)})


# 1 & 2. Topic-only and Topic + reference_text regression checks

def test_topic_only_and_topic_with_reference_preserve_existing_behavior(course_setup):
    fake_model_server.STATE["mode"] = "clean"
    lec, c, subj, t = course_setup["lec"], course_setup["course"], course_setup["subject"], course_setup["topic"]

    r1 = lec.post("/api/lecturer/generate", json={
        "course_id": c["id"], "subject_id": subj["id"], "topic_id": t["id"],
        "title": "Topic only quiz", "question_count": 2, "difficulty": "medium",
    })
    assert r1.status_code == 202, r1.text
    run1 = wait_run(lec, r1.json()["run_id"], timeout=30)
    assert run1["status"] == "done" and run1["ready"] == 2
    assert run1["grounded_on"] == "generated_notes"
    assert run1["source_mode"] == "topic"

    r2 = lec.post("/api/lecturer/generate", json={
        "course_id": c["id"], "subject_id": subj["id"], "topic_id": t["id"],
        "title": "Topic + notes quiz", "question_count": 2, "difficulty": "easy",
        "source_mode": "topic", "reference_text": SCHEDULING_DOC,
    })
    assert r2.status_code == 202, r2.text
    run2 = wait_run(lec, r2.json()["run_id"], timeout=30)
    assert run2["status"] == "done" and run2["ready"] == 2
    assert run2["grounded_on"] == "reference_text"
    q_items = lec.get(f"/api/lecturer/quizzes/{run2['quiz_id']}").json()["items"]
    assert all(it["question"]["source_type"] == "reference_text" for it in q_items)


# 3, 4, 5, 11, 14. PDF, DOCX, TXT extraction + Lecturer & Student generation + source references + Groq/Qwen

def test_pdf_upload_and_lecturer_grounded_generation_with_source_refs(course_setup, app):
    fake_model_server.STATE["mode"] = "clean"
    lec, c, subj, t = course_setup["lec"], course_setup["course"], course_setup["subject"], course_setup["topic"]
    pdf_bytes = make_pdf([
        "Chapter 1 Scheduling Overview\n" + SCHEDULING_DOC.split("# Unit 2")[0].replace("# ", ""),
        "Chapter 2 Priority and Aging\n" + SCHEDULING_DOC.split("# Unit 2")[1].lstrip(": "),
    ])
    up = _upload(lec, "scheduling_notes.pdf", pdf_bytes, "application/pdf")
    assert up.status_code == 200, up.text
    meta = up.json()
    assert meta["file_type"] == "pdf" and meta["page_count"] == 2 and meta["word_count"] >= 90
    assert meta["chunk_count"] >= 1

    gen = lec.post("/api/lecturer/generate", json={
        "course_id": c["id"], "subject_id": subj["id"], "topic_id": t["id"],
        "title": "PDF Grounded Quiz", "question_count": 2, "difficulty": "medium",
        "source_mode": "document", "document_id": meta["document_id"],
        "focus_topic": "Round robin and aging",
    })
    assert gen.status_code == 202, gen.text
    run = wait_run(lec, gen.json()["run_id"], timeout=30)
    assert run["status"] == "done" and run["ready"] == 2
    assert run["grounded_on"] == "document"
    assert run["document_name"] == "scheduling_notes.pdf"

    # Ephemeral doc was consumed once launched (no lingering duplicate storage)
    assert app.state.documents.get(meta["document_id"], 1) is None

    quiz = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()
    assert quiz["status"] == "draft"
    for item in quiz["items"]:
        q = item["question"]
        assert q["review_status"] == "draft"           # still requires lecturer approval
        assert q["source_type"] == "document"
        assert q["source_excerpt"] and len(q["source_excerpt"]) > 20
        assert q["source_ref"] is not None
        assert q["source_ref"]["document_name"] == "scheduling_notes.pdf"
        assert q["source_ref"]["page"] in (1, 2)
        assert q["validation"]["quality"]["status"] == "passed"
        assert q["validation"]["grounding_verified"] is True

    # Audit log AgentRun captured document mode
    with app.state.db.session() as db:
        ar = db.query(AgentRun).filter(AgentRun.generation_run_id == run["run_id"]).first()
        assert ar is not None
        assert ar.input.get("source_mode") == "document"
        assert ar.input.get("document_name") == "scheduling_notes.pdf"


def test_docx_upload_extracts_headings_and_tables_and_student_practice_shows_source_ref(course_setup):
    fake_model_server.STATE["mode"] = "clean"
    st = course_setup["st"]
    doc_bytes = make_docx(
        [
            ("Scheduling Fundamentals", [
                "CPU scheduling chooses which process uses the processor in time-sharing systems.",
                "Round robin gives each job a time quantum; smaller quanta increase context switch cost.",
                "Shortest job first minimises waiting time but requires knowing burst length in advance.",
            ]),
            ("Starvation Mitigation", [
                "Priority scheduling and shortest job first can starve long jobs or low-priority tasks if shorter jobs continue arriving repeatedly.",
                "Aging prevents starvation in CPU scheduling by gradually increasing the priority of waiting processes over time in ready queues.",
                "Multilevel feedback queues move processes dynamically between priority queues based on observed burst length and interactive I/O waiting behaviour.",
            ]),
        ],
        table_rows=[("Scheduler", "Key Trait"), ("Round Robin", "Uses a fixed time quantum")],
    )
    up = _upload(st, "lecture.docx", doc_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert up.status_code == 200, up.text
    meta = up.json()
    assert meta["file_type"] == "docx"
    assert "Scheduling Fundamentals" in meta["headings"]
    assert meta["word_count"] >= 55

    gen = st.post("/api/student/practice/generate", json={
        "source_mode": "document",
        "document_id": meta["document_id"],
        "document_section": "Starvation Mitigation",
        "question_count": 5,
        "difficulty": "adaptive",
    })
    assert gen.status_code == 202, gen.text
    run = wait_run(st, gen.json()["run_id"], timeout=30)
    assert run["status"] in ("done", "partial") and run["ready"] >= 1
    assert run["grounded_on"] == "document"

    # Student starts, submits, and reviews result with source_ref
    sess = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
    res = st.post(f"/api/student/attempts/{sess['session_id']}/submit").json()
    assert len(res["items"]) >= 1
    assert res["items"][0]["source_ref"]["document_name"] == "lecture.docx"
    assert res["items"][0]["source_excerpt"]


def test_txt_upload_extracts_markdown_headings(course_setup):
    st = course_setup["st"]
    up = _upload(st, "notes.txt", SCHEDULING_DOC.encode("utf-8"), "text/plain")
    assert up.status_code == 200, up.text
    meta = up.json()
    assert meta["file_type"] == "txt"
    assert any("CPU Scheduling" in h for h in meta["headings"])


# 6. Long document chunking & selection

def test_long_document_chunking_preserves_all_sections_and_selects_relevant_chunks():
    # Build >18,000 chars across 12 PDF pages so truncation at 12,000 chars would lose later chapters
    pages = []
    for p in range(1, 13):
        if p == 10:
            body = (
                "Page 10 Special Section: Virtual Memory Paging and TLB Lookups\n"
                + ("Virtual memory translates virtual addresses into physical frames using page tables and a fast translation lookaside buffer cache. " * 22)
            )
        else:
            body = (
                f"Chapter {p}: Operating Systems Basics Part {p}\n"
                + (f"This general chapter number {p} discusses kernel interrupts, device drivers, and buffered disk block scheduling policies. " * 18)
            )
        pages.append(body)
    pdf_bytes = make_pdf(pages)
    doc = extract_document("textbook.pdf", "application/pdf", pdf_bytes)
    assert doc.page_count == 12
    assert len(doc.chunks) >= 8
    # Verify later page 10 wasn't truncated away (>12k chars total)
    assert sum(len(c.text) for c in doc.chunks) > 15000
    assert any(c.page == 10 and "translation lookaside buffer" in c.text.lower() for c in doc.chunks)

    sel = select_chunks(doc, question_count=4, topic="virtual memory paging translation lookaside buffer", difficulty="hard")
    assert sel.effective_count == 4
    assert any(c.page == 10 for c in sel.chunks), "Relevant chunk on later page must be selected"


# 7, 8, 9. Empty, corrupted, unsupported, macro, oversized, scanned PDF

def test_upload_rejects_empty_corrupted_unsupported_macro_oversized_and_scanned_pdfs(course_setup, settings):
    lec = course_setup["lec"]

    # Empty
    assert _upload(lec, "empty.txt", b"", "text/plain").status_code == 422
    assert _upload(lec, "blank.txt", b"   \n\t  ", "text/plain").status_code == 422

    # Corrupted PDF & DOCX
    r_bad_pdf = _upload(lec, "corrupt.pdf", b"%PDF-1.4\nnot-a-valid-xref-table!!!", "application/pdf")
    assert r_bad_pdf.status_code == 422
    r_bad_docx = _upload(lec, "corrupt.docx", b"PK\x03\x04corrupted_zip_payload", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert r_bad_docx.status_code == 422

    # Unsupported extension & legacy .doc & macro .docm
    assert _upload(lec, "malware.exe", b"MZ\x90\x00hello").status_code == 415
    assert _upload(lec, "legacy.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"word " * 30).status_code == 415
    assert _upload(lec, "macros.docm", b"PK\x03\x04...").status_code == 415

    # Renamed executable disguised as .pdf or .txt (magic-byte/binary rejection)
    assert _upload(lec, "fake.pdf", b"MZ\x90\x00not a pdf").status_code in (415, 422)
    assert _upload(lec, "binary.txt", b"MZ\x90\x00\x00\x01binary executable bytes").status_code in (415, 422)

    # DOCX containing VBA macros inside zip must be blocked
    valid_docx = make_docx([("Notes", ["Some clean words " * 25])])
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(valid_docx), "r") as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("word/vbaProject.bin", b"macro-code")
    r_vba = _upload(lec, "with_macro.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert r_vba.status_code == 422
    assert "macro" in r_vba.json()["detail"].lower()

    # Scanned PDF without selectable text -> must report OCR not supported
    scanned_pdf = make_pdf(["", ""], image_only=True)
    r_scan = _upload(lec, "scanned.pdf", scanned_pdf, "application/pdf")
    assert r_scan.status_code == 422
    assert "ocr is not supported" in r_scan.json()["detail"].lower()

    # Oversized >10 MB payload rejected cleanly
    too_big = b"A" * (settings.max_document_bytes + 64)
    r_big = _upload(lec, "huge.txt", too_big, "text/plain")
    assert r_big.status_code == 413


# 10. Insufficient content handling

def test_insufficient_document_content_reduces_count_or_returns_clear_error(course_setup):
    fake_model_server.STATE["mode"] = "clean"
    lec, c, subj, t = course_setup["lec"], course_setup["course"], course_setup["subject"], course_setup["topic"]

    # Too short (< 40 words) -> extract warns (recommended_max_questions=0) and generation rejects cleanly with 422
    r_tiny = _upload(lec, "tiny.txt", b"Too brief to form questions.", "text/plain")
    assert r_tiny.status_code == 200, r_tiny.text
    tiny_meta = r_tiny.json()
    assert tiny_meta["recommended_max_questions"] == 0
    assert "40 words" in (tiny_meta["warning"] or "")
    r_tiny_gen = lec.post("/api/lecturer/generate", json={
        "course_id": c["id"], "subject_id": subj["id"], "topic_id": t["id"],
        "title": "Tiny Doc Fail", "question_count": 3, "difficulty": "mixed",
        "source_mode": "document", "document_id": tiny_meta["document_id"],
    })
    assert r_tiny_gen.status_code == 422
    assert "insufficient content" in r_tiny_gen.json()["detail"].lower()

    # Valid short doc (~70 words -> supports ~3 questions) when requesting 10 questions
    short_doc = (
        "Round robin scheduling rotates the CPU across ready tasks using a small time quantum so every interactive session progresses cleanly. "
        "Shortest job first lowers average waiting time while aging increases priority to prevent starvation in priority schedulers. "
        "Context switch cost grows if the time quantum shrinks too far in time-sharing operating systems."
    )
    up = _upload(lec, "short_notes.txt", short_doc.encode("utf-8"), "text/plain")
    assert up.status_code == 200, up.text
    meta = up.json()
    assert meta["recommended_max_questions"] < 10

    gen = lec.post("/api/lecturer/generate", json={
        "course_id": c["id"], "subject_id": subj["id"], "topic_id": t["id"],
        "title": "Short Doc Cap", "question_count": 10, "difficulty": "mixed",
        "source_mode": "document", "document_id": meta["document_id"],
    })
    assert gen.status_code == 202, gen.text
    run = wait_run(lec, gen.json()["run_id"], timeout=30)
    assert run["requested_count"] == 10
    assert run["supported_count"] < 10
    assert run["total"] == run["supported_count"]
    assert "insufficient document material" in (run["insufficient_content_note"] or "").lower()


# 12. Unsupported question rejection & proving Groq approval cannot override missing grounding

def test_ungrounded_question_is_rejected_even_when_groq_returns_passed(settings):
    mcq_off_topic = {
        "question": "Which protocol resolves IPv4 addresses into Ethernet MAC hardware frames?",
        "options": ["ARP cache lookup", "BGP routing loop", "TLS handshake cipher", "DNS root server"],
        "answer": "A",
        "explanation": "Address Resolution Protocol maps network layer addresses onto Ethernet links.",
    }
    ok, g_score, info = verify_source_grounding(mcq_off_topic, BIO_DOC, strict=True)
    assert ok is False and info["rules_reason"] == "not_grounded" and g_score < 0.25

    # Hallucinated numeric constant (e.g. 4096) not supported in source passage
    mcq_fake_num = {
        "question": "How many kilobytes does cellular DNA require during transcription using nucleotide bases?",
        "options": ["4096 kilobytes", "512 kilobytes", "128 kilobytes", "64 kilobytes"],
        "answer": "A",
        "explanation": "Messenger RNA requires 4096 kilobytes.",
    }
    ok_num, _, info_num = verify_source_grounding(mcq_fake_num, BIO_DOC, strict=True)
    assert ok_num is False and info_num["rules_reason"] == "not_grounded" and "4096" in info_num["ungrounded_numbers"]

    # Prove Validator enforces strict grounding when parsing raw output
    val = Validator(settings, ModelService(settings))
    raw_off_topic = (
        f"question: {mcq_off_topic['question']} "
        f"options: (A) {mcq_off_topic['options'][0]} (B) {mcq_off_topic['options'][1]} "
        f"(C) {mcq_off_topic['options'][2]} (D) {mcq_off_topic['options'][3]} "
        f"answer: {mcq_off_topic['answer']} explanation: {mcq_off_topic['explanation']}"
    )
    chk = val.check(raw_off_topic, [], BIO_DOC, grounded=True, strict_grounding=True)
    assert not chk.ok and chk.reason == "not_grounded"

    # Prove QualityEvaluator NEVER lets Groq passed=True override grounding_verified=False
    fake_grok_server.reset("pass")
    ev = QualityEvaluator(settings)
    try:
        res = ev.evaluate(
            mcq_off_topic, "Biology", "Genetics", "medium", passage=BIO_DOC,
            rules_info={"math_status": "not_math", "math_verified": False, "grounding_verified": False},
            strict_source=True,
        )
        assert res.ai_called is True
        assert fake_grok_server.STATE["calls"] == 1
        assert res.ai["passed"] is True                # Groq itself said passed=true
        assert res.passed is False                      # Yet evaluator rejected due to failed grounding
        assert res.reason == "not_grounded"
    finally:
        ev.close()


def test_lecturer_keeps_ungrounded_as_failed_draft_and_blocks_publish_while_student_drops_them(course_setup):
    fake_model_server.STATE["mode"] = "clean"
    lec, st = course_setup["lec"], course_setup["st"]
    c, subj, t = course_setup["course"], course_setup["subject"], course_setup["topic"]

    # Upload Biology DNA document, while fake_model_server emits OS scheduling questions -> 0% grounded!
    up_lec = _upload(lec, "biology.txt", BIO_DOC.encode("utf-8"), "text/plain")
    assert up_lec.status_code == 200
    gen_lec = lec.post("/api/lecturer/generate", json={
        "course_id": c["id"], "subject_id": subj["id"], "topic_id": t["id"],
        "title": "Mismatched Biology", "question_count": 2, "difficulty": "medium",
        "source_mode": "document", "document_id": up_lec.json()["document_id"],
    })
    assert gen_lec.status_code == 202
    run_lec = wait_run(lec, gen_lec.json()["run_id"], timeout=30)
    assert run_lec["rejected"].get("not_grounded", 0) >= 1
    quiz = lec.get(f"/api/lecturer/quizzes/{run_lec['quiz_id']}").json()
    for it in quiz["items"]:
        q = it["question"]
        assert q["review_status"] == "draft"
        assert q["validation"]["failed_validation"] is True
        assert q["validation"]["failure_reason"] == "not_grounded"
    # Publishing without lecturer review approval MUST fail 422
    pub = lec.post(f"/api/lecturer/quizzes/{run_lec['quiz_id']}/publish")
    assert pub.status_code == 422

    # Student practice rejects ungrounded questions so none reach the student quiz
    up_st = _upload(st, "biology.txt", BIO_DOC.encode("utf-8"), "text/plain")
    assert up_st.status_code == 200
    gen_st = st.post("/api/student/practice/generate", json={
        "source_mode": "document",
        "document_id": up_st.json()["document_id"],
        "question_count": 5,
        "difficulty": "medium",
    })
    assert gen_st.status_code == 202
    run_st = wait_run(st, gen_st.json()["run_id"], timeout=30)
    assert run_st["ready"] == 0
    assert run_st["rejected"].get("not_grounded", 0) >= 1


# 13. Privacy, authorization & no permanent file writes on disk

def test_document_privacy_and_role_authorization(course_setup, tmp_path):
    lec, st = course_setup["lec"], course_setup["st"]
    make_client = course_setup["make_client"]
    other_st = make_client()
    register(other_st, "student", name="Student Two")
    anon = make_client()

    txt = SCHEDULING_DOC.encode("utf-8")
    # Unauthenticated access rejected
    assert _upload(anon, "notes.txt", txt, "text/plain").status_code == 401
    assert anon.delete("/api/documents/nonexistent").status_code == 401

    # Lecturer uploads doc -> student cannot steal document_id
    doc_lec = _upload(lec, "lec_notes.txt", txt, "text/plain").json()["document_id"]
    r_steal_st = st.post("/api/student/practice/generate", json={
        "source_mode": "document", "document_id": doc_lec, "question_count": 5,
    })
    assert r_steal_st.status_code == 404

    # Student 1 uploads doc -> Student 2 cannot delete or use it, and student cannot call lecturer endpoint
    doc_st = _upload(st, "st_notes.txt", txt, "text/plain").json()["document_id"]
    assert other_st.delete(f"/api/documents/{doc_st}").status_code == 404
    assert other_st.post("/api/student/practice/generate", json={
        "source_mode": "document", "document_id": doc_st, "question_count": 5,
    }).status_code == 404
    assert st.post("/api/lecturer/generate", json={
        "course_id": course_setup["course"]["id"], "subject_id": course_setup["subject"]["id"],
        "topic_id": course_setup["topic"]["id"], "title": "Nope", "question_count": 1,
        "source_mode": "document", "document_id": doc_st,
    }).status_code == 403

    # Owner can discard their own staged document explicitly
    assert st.delete(f"/api/documents/{doc_st}").status_code == 204
    assert st.delete(f"/api/documents/{doc_st}").status_code == 404

    # Verify only test.db exists in tmp_path (no permanent upload files saved on disk)
    files_on_disk = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert not any(name.endswith((".pdf", ".docx", ".txt")) for name in files_on_disk)
