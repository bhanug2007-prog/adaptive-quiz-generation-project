import { Check, ChevronRight, ClipboardCheck, FileDown, FileSpreadsheet, FolderTree, Grid3x3, Library, Scale, ShieldCheck, Sparkles, SearchCheck } from 'lucide-react'
import Reveal, { SectionHead } from './Reveal'

const BENEFITS = [
  'Generate and edit question sets faster',
  'Assign assessments to enrolled students',
  'Review completion and performance',
  'Compare mastery across topics',
  'Identify frequently missed questions',
  'Detect topics needing classroom revision',
  'Track changes across multiple assessments',
  'Export approved quiz content and performance reports',
]

const FLOW = [
  { icon: Sparkles, label: 'Generate', tone: 'accent' },
  { icon: ShieldCheck, label: 'Automatic checks', tone: 'neutral' },
  { icon: ClipboardCheck, label: 'You review and edit', tone: 'neutral' },
  { icon: Check, label: 'Approve and publish', tone: 'teal' },
]

const TOOLS = [
  { icon: FolderTree, title: 'Course structure', text: 'Course, subject, unit and topic, so every question and result has a place.' },
  { icon: Sparkles, ai: true, title: 'AI quiz builder', text: 'Generate a draft from topics or your own notes, then review each question.' },
  { icon: Library, title: 'Question bank', text: 'Keep approved questions, edit them, and reuse them across assessments.' },
  { icon: Scale, title: 'Publishing with weighting', text: 'Set how much each assessment counts, with caps so totals stay sensible.' },
  { icon: Grid3x3, title: 'Class analytics and heatmap', text: 'Student-by-topic mastery at a glance, with participation and score trends.' },
  { icon: SearchCheck, title: 'Question quality', text: 'Flags questions that are almost always missed, often skipped or mislabelled for difficulty, only after at least 10 answers.' },
  { icon: FileSpreadsheet, title: 'CSV reports', text: 'Download results and topic mastery for your own records.' },
  { icon: FileDown, title: 'Google Forms export', text: 'Integration code is written but not yet tested against Google. A manual export is available today.' },
]

export default function Lecturers() {
  return (
    <section id="lecturers" className="lp-section lp-section--band" aria-labelledby="lp-lect-title">
      <div className="container">
        <SectionHead id="lp-lect-title" eyebrow="For lecturers"
          title="Less time writing quizzes. More time teaching what was missed."
          lead="AI drafts the questions. You stay in charge of what students see." />

        <Reveal className="lp-flow" aria-label="Question review flow">
          {FLOW.map((f, i) => (
            <div key={f.label} className="lp-flow__step-wrap">
              <div className={`lp-flow__step lp-tone-${f.tone}`}>
                <f.icon size={15} aria-hidden="true" />{f.label}
              </div>
              {i < FLOW.length - 1 && <ChevronRight size={16} className="lp-flow__sep" aria-hidden="true" />}
            </div>
          ))}
        </Reveal>
        <p className="lp-note lp-note--center">Every question must be approved by a lecturer before an assessment is published.</p>

        <div className="lp-split lp-split--lect">
          <Reveal className="lp-split__a">
            <h3 className="lp-h3 lp-mb">What you can do</h3>
            <ul className="lp-checks lp-checks--one">
              {BENEFITS.map((b) => <li key={b}><Check size={15} aria-hidden="true" />{b}</li>)}
            </ul>
          </Reveal>
          <ul className="lp-tools">
            {TOOLS.map((t, i) => (
              <Reveal as="li" key={t.title} delay={(i % 2) * 60} className={`lp-tool ${t.ai ? 'lp-tool--ai' : ''}`}>
                <t.icon size={16} aria-hidden="true" className="lp-tool__icon" />
                <div>
                  <h4 className="lp-tool__title">{t.title}</h4>
                  <p>{t.text}</p>
                </div>
              </Reveal>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
