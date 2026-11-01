import { Check } from 'lucide-react'

export const BUILDER_STEPS = ['Topic & setup', 'Generate', 'Review questions', 'Settings', 'Preview & publish']

/** Builder progress. current is a 0-based index; done steps get a check. onStep(i) makes earlier/later steps clickable. */
export default function Stepper({ steps = BUILDER_STEPS, current, onStep, enabled = () => false }) {
  return (
    <ol className="lc-stepper" aria-label="Quiz builder steps">
      {steps.map((s, i) => {
        const state = i < current ? 'done' : i === current ? 'current' : 'todo'
        const clickable = onStep && enabled(i) && i !== current
        const inner = (
          <>
            <span className="lc-stepper__dot" aria-hidden="true">{state === 'done' ? <Check size={13} /> : i + 1}</span>
            <span className="lc-stepper__label">{s}</span>
          </>
        )
        return (
          <li key={s} data-state={state} aria-current={state === 'current' ? 'step' : undefined}>
            {clickable ? <button type="button" onClick={() => onStep(i)}>{inner}<span className="visually-hidden"> (go to step)</span></button> : <span className="lc-stepper__static">{inner}</span>}
          </li>
        )
      })}
    </ol>
  )
}
