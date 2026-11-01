import { useModelHealth } from '../hooks/useModelHealth'

const TEXT = { ok: 'Qwen 7B online', loading: 'Model loading', offline: 'Model offline', error: 'Model error', checking: 'Checking model' }
const COLOR = { ok: 'var(--success)', loading: 'var(--warning)', offline: 'var(--error)', error: 'var(--error)', checking: 'var(--text-3)' }

/** Small badge: is the question-generation model reachable? Quizzes still work when it is offline. */
export default function ModelStatus() {
  const h = useModelHealth()
  return (
    <span className="model-status" title={h.detail || TEXT[h.state]} role="status">
      <span className="dot" style={{ color: COLOR[h.state] }} aria-hidden="true" />
      {TEXT[h.state]}
    </span>
  )
}
