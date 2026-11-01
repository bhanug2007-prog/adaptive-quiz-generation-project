import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { ClosingCta, Experience, Features, Hero, HowItWorks, ProductInAction } from '../../components/landing/site/Sections'
import { useReveal } from '../../components/landing/site/motion'

export default function Landing() {
  const { hash } = useLocation()
  const root = useRef(null)
  useReveal(root)

  useEffect(() => {
    document.title = 'AdaptiveIQ · Quizzes, topic mastery and adaptive practice'
  }, [])

  // The page is lazy-loaded, so the browser's own jump to /#section can happen before the
  // section exists. Scroll once it has rendered.
  useEffect(() => {
    if (!hash) return
    const el = document.getElementById(hash.slice(1))
    if (el) el.scrollIntoView({ block: 'start' })
  }, [hash])

  return (
    <div className="site-page" ref={root}>
      <Hero />
      <ProductInAction />
      <Features />
      <Experience />
      <HowItWorks />
      <ClosingCta />
    </div>
  )
}
