import { ArrowRight, LogIn } from 'lucide-react'
import { Button } from '../ui'

/** Calm hero: what AdaptiveIQ is, in one sentence, and two ways in. */
export default function GuideHero() {
  return (
    <section className="lp2-hero" aria-labelledby="lp2-hero-title">
      <div className="container lp2-hero__inner lp2-fade">
        <p className="lp-eyebrow">AdaptiveIQ</p>
        <h1 id="lp2-hero-title" className="lp2-hero__title">Quizzes that show each student what to practise next.</h1>
        <p className="lp2-hero__lead">
          Lecturers build quizzes with AI help and approve every question. Students take them, practise on their own,
          and see an estimate of how well they know each topic.
        </p>
        <div className="lp2-hero__ctas">
          <Button variant="primary" size="lg" to="/register" iconRight={ArrowRight}>Get started</Button>
          <Button size="lg" to="/signin" icon={LogIn}>Sign in</Button>
        </div>
        <nav className="lp2-jump" aria-label="On this page">
          <a href="#adaptive">For students</a>
          <a href="#lecturers">For lecturers</a>
          <a href="#how">How it works</a>
          <a href="#try">Try it yourself</a>
        </nav>
      </div>
    </section>
  )
}
