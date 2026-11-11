import { useId, useMemo, useRef, useState } from 'react'
import { FileText, Trash2, Upload } from 'lucide-react'
import { documentsApi } from '../../api/endpoints'
import { Alert, Badge, Button, Field, Select } from '../ui'

export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
const ACCEPTED_EXTS = ['.pdf', '.docx', '.txt']

function formatBytes(n) {
  if (!Number.isFinite(n) || n <= 0) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function fileExtension(name) {
  const s = String(name || '').toLowerCase()
  const idx = s.lastIndexOf('.')
  return idx >= 0 ? s.slice(idx) : ''
}

/**
 * File picker + upload/extraction summary for PDF, DOCX and TXT study material.
 * Raw file bytes are sent to /api/documents/extract once; the returned document_id
 * stages extracted chunks privately for the subsequent generation request.
 */
export default function DocumentSourcePicker({
  doc,
  onDocChange,
  section,
  onSectionChange,
  busy = false,
  onBusyChange,
  externalError = null,
}) {
  const inputId = useId()
  const inputRef = useRef(null)
  const [localError, setLocalError] = useState(null)
  const [pendingName, setPendingName] = useState('')

  const sectionOptions = useMemo(() => {
    if (!doc) return []
    const combined = [...(doc.sections || []), ...(doc.headings || [])]
    return [...new Set(combined.map((x) => String(x || '').trim()).filter(Boolean))]
  }, [doc])

  const shownError = localError || externalError

  const handleFile = async (file) => {
    if (!file) return
    setLocalError(null)
    const ext = fileExtension(file.name)
    if (!ACCEPTED_EXTS.includes(ext)) {
      setLocalError('Unsupported file format. Upload a PDF, DOCX, or TXT file.')
      if (inputRef.current) inputRef.current.value = ''
      return
    }
    if (file.size === 0) {
      setLocalError('The selected file is empty.')
      if (inputRef.current) inputRef.current.value = ''
      return
    }
    if (file.size > MAX_DOCUMENT_BYTES) {
      setLocalError(`File is too large (${formatBytes(file.size)}). Maximum allowed size is 10 MB.`)
      if (inputRef.current) inputRef.current.value = ''
      return
    }

    const previousId = doc?.document_id
    setPendingName(file.name)
    onBusyChange?.(true)
    try {
      const extracted = await documentsApi.extract(file)
      if (previousId && previousId !== extracted.document_id) {
        documentsApi.remove(previousId).catch(() => {})
      }
      onSectionChange?.('')
      onDocChange?.(extracted)
    } catch (err) {
      onSectionChange?.('')
      onDocChange?.(null)
      setLocalError(err?.message || 'Could not extract text from this file.')
    } finally {
      setPendingName('')
      onBusyChange?.(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const removeDoc = () => {
    const id = doc?.document_id
    setLocalError(null)
    onSectionChange?.('')
    onDocChange?.(null)
    if (inputRef.current) inputRef.current.value = ''
    if (id) documentsApi.remove(id).catch(() => {})
  }

  return (
    <div className="doc-picker stack">
      <div className="field">
        <label className="field__label" htmlFor={inputId}>Study material file (PDF, DOCX, TXT)</label>
        <div className="doc-picker__box">
          <div className="doc-picker__control">
            <input
              ref={inputRef}
              id={inputId}
              className="doc-picker__input"
              type="file"
              accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              disabled={busy}
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
            <span className="doc-picker__hint faint">
              <Upload size={14} aria-hidden="true" />
              <span>PDF, DOCX or TXT · Max 10 MB · Scanned image PDFs without selectable text are not supported.</span>
            </span>
          </div>
          {busy && (
            <div className="doc-picker__status" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              <span>Uploading and extracting text from {pendingName || 'document'}…</span>
            </div>
          )}
        </div>
      </div>

      {shownError && (
        <Alert tone="error" title="Document problem">
          {shownError}
        </Alert>
      )}

      {doc && (
        <div className="doc-card stack">
          <div className="row-between" style={{ gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            <div className="row" style={{ gap: 'var(--space-2)', minWidth: 0 }}>
              <FileText size={18} aria-hidden="true" style={{ color: 'var(--accent)', flex: 'none' }} />
              <strong className="doc-card__name">{doc.filename}</strong>
              <Badge tone="accent">{String(doc.file_type || '').toUpperCase()}</Badge>
              <Badge>{formatBytes(doc.size_bytes)}</Badge>
            </div>
            <Button type="button" size="sm" variant="ghost" icon={Trash2} onClick={removeDoc} disabled={busy}>
              Remove file
            </Button>
          </div>

          <p className="doc-card__meta">
            {doc.page_count ? `${doc.page_count} ${doc.page_count === 1 ? 'page' : 'pages'} · ` : ''}
            {doc.word_count.toLocaleString()} words · {doc.chunk_count} {doc.chunk_count === 1 ? 'chunk' : 'chunks'} ·
            supports up to ~{doc.recommended_max_questions} questions
          </p>

          {doc.warning && <Alert tone="warning">{doc.warning}</Alert>}

          {sectionOptions.length > 0 && (
            <Field
              label="Chapter or section (optional)"
              hint="Filter generation to one heading or section, or use the whole document."
            >
              {(a) => (
                <Select {...a} value={section || ''} onChange={(e) => onSectionChange?.(e.target.value)}>
                  <option value="">All sections (entire document)</option>
                  {sectionOptions.map((sec) => (
                    <option key={sec} value={sec}>{sec}</option>
                  ))}
                </Select>
              )}
            </Field>
          )}

          {doc.preview && (
            <details className="doc-card__preview">
              <summary>Extracted text preview</summary>
              <blockquote className="lc-excerpt">{doc.preview}</blockquote>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
