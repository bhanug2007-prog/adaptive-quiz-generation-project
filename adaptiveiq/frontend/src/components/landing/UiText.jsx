/** Renders text where [[Label]] marks a real menu, tab or button name in the app. */
export default function UiText({ text }) {
  const parts = text.split(/(\[\[[^\]]+\]\])/g)
  return parts.map((p, i) => (p.startsWith('[[') && p.endsWith(']]')
    ? <span key={i} className="lp2-ui">{p.slice(2, -2)}</span>
    : p))
}
