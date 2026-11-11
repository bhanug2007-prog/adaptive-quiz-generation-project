"""Private document upload & text extraction endpoints (PDF, DOCX, TXT)."""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.core.config import Settings
from app.core.deps import get_settings_dep, require_verified
from app.models import User
from app.services import permissions as perm
from app.services.document_service import DocumentError, extract_document

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentExtractOut(BaseModel):
    document_id: str
    filename: str
    file_type: str
    size_bytes: int
    page_count: int | None
    word_count: int
    chunk_count: int
    sections: list[str]
    headings: list[str]
    recommended_max_questions: int
    warning: str | None = None
    preview: str


@router.post("/extract", response_model=DocumentExtractOut)
async def extract_upload(
    request: Request,
    file: UploadFile | None = File(default=None),
    user: User = Depends(require_verified),
    s: Settings = Depends(get_settings_dep),
):
    if file is None:
        raise HTTPException(422, "Select a PDF, DOCX, or TXT file to upload.")
    max_bytes = s.max_document_bytes
    pieces: list[bytes] = []
    total = 0
    data = b""
    try:
        while True:
            piece = await file.read(65536)
            if not piece:
                break
            total += len(piece)
            if total > max_bytes:
                mb = max(1, max_bytes // (1024 * 1024))
                raise HTTPException(413, f"File is too large. Maximum allowed size is {mb} MB.")
            pieces.append(piece)
        data = b"".join(pieces)
    finally:
        pieces.clear()
        await file.close()

    try:
        doc = extract_document(
            file.filename,
            file.content_type,
            data,
            max_bytes=max_bytes,
            min_words_per_q=s.min_words_per_document_question,
            min_doc_words=s.min_document_words,
        )
    except DocumentError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    finally:
        data = b""

    doc_id = request.app.state.documents.put(user.id, doc)
    sections = list(dict.fromkeys((c.section or c.heading) for c in doc.chunks if (c.section or c.heading)))[:50]
    return DocumentExtractOut(
        document_id=doc_id,
        filename=doc.document_name,
        file_type=doc.file_type,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        word_count=doc.word_count,
        chunk_count=len(doc.chunks),
        sections=sections,
        headings=doc.headings,
        recommended_max_questions=doc.recommended_max_questions,
        warning=doc.warning,
        preview=doc.preview,
    )


@router.delete("/{document_id}", status_code=204)
def discard_upload(document_id: str, request: Request, user: User = Depends(require_verified)):
    if not request.app.state.documents.delete(document_id, user.id):
        raise perm.not_found("Document")
