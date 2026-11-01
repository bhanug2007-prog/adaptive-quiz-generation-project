import { ShieldCheck, Sparkles } from 'lucide-react'
import { Badge } from '../ui'
import { STATE_META } from './helpers'

/** Quiz state from the API (upcoming/open/in_progress/late_open/submitted/expired). */
export function QuizStateBadge({ state }) {
  const m = STATE_META[state] || { text: state }
  return <Badge tone={m.tone}>{m.text}</Badge>
}

/** Practice quizzes are AI-generated and not reviewed by a lecturer; assessments are reviewed. */
export function KindBadge({ kind, long }) {
  if (kind === 'practice') {
    return (
      <Badge tone="accent" icon={Sparkles} title="Written by the AI model for your practice. No lecturer has reviewed these questions.">
        {long ? 'AI-generated practice · not reviewed by a lecturer' : 'AI practice · not lecturer-reviewed'}
      </Badge>
    )
  }
  return <Badge icon={ShieldCheck} title="Every question was reviewed by your lecturer.">{long ? 'Assessment · reviewed by your lecturer' : 'Lecturer-reviewed'}</Badge>
}
