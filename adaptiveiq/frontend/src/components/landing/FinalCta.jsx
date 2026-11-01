import { ArrowRight, LogIn } from 'lucide-react'
import { Button } from '../ui'
import Reveal from './Reveal'

export default function FinalCta() {
  return (
    <section className="lp-section lp-section--cta" aria-labelledby="lp-cta-title">
      <div className="container">
        <Reveal className="lp-cta">
          <h2 id="lp-cta-title" className="lp-h2">Ready to try it?</h2>
          <p className="lp-lead">Create an account as a student, or as a lecturer with your institution’s invite code.</p>
          <div className="lp2-hero__ctas lp-cta__btns">
            <Button variant="primary" size="lg" to="/register" iconRight={ArrowRight}>Get started</Button>
            <Button size="lg" to="/signin" icon={LogIn}>Sign in</Button>
          </div>
          <p className="lp-cta__credit">A DSAI team project at IIIT Dharwad.</p>
        </Reveal>
      </div>
    </section>
  )
}
