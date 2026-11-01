import { useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, BookOpen, CalendarClock, ChartColumn, CircleCheck, ClipboardCheck, ClipboardList, FileCheck,
  GraduationCap, ListChecks, NotebookPen, Presentation, Target, TrendingUp,
} from 'lucide-react'
import {
  AdaptiveMock, AnalyticsMock, ApprovalMock, CreateMock, GeneratedMock, HeatmapMock, MasteryMock, PlayerMock, Preview, QuizMock, RevisionMock,
} from './Mockups'
import { Tilt, useParallax } from './motion'

function SectionHead({ eyebrow, title, lead, id, align = 'left' }) {
  return (
    <header className={`s-head s-head--${align}`} data-reveal>
      {eyebrow && <p className="s-eyebrow">{eyebrow}</p>}
      <h2 id={id}>{title}</h2>
      {lead && <p className="s-lead">{lead}</p>}
    </header>
  )
}

/* A — hero */
export function Hero() {
  const grid = useRef(null)
  useParallax(grid, -0.08, 40)
  return (
    <section className="s-hero" aria-labelledby="hero-title">
      <div className="s-hero__grid-bg" ref={grid} aria-hidden="true" />
      <div className="s-wrap s-hero__layout">
        <div className="s-hero__copy">
          <p className="s-eyebrow" data-reveal>Learn smarter</p>
          <h1 id="hero-title" data-reveal style={{ '--d': 1 }}>Turn your syllabus into a smarter way to learn.</h1>
          <p className="s-hero__lead" data-reveal style={{ '--d': 2 }}>
            Generate quizzes, track topic mastery, and focus on what you need to improve.
          </p>
          <div className="s-actions" data-reveal style={{ '--d': 3 }}>
            <Link className="s-btn s-btn--primary" to="/register">Get Started<ArrowRight size={16} aria-hidden="true" /></Link>
            <a className="s-btn s-btn--ghost" href="#product">Explore the Platform</a>
          </div>
          <p className="s-hero__note" data-reveal style={{ '--d': 4 }}>
            Already have an account? <Link to="/signin">Sign in</Link>
          </p>
        </div>
        <div className="s-hero__visual" data-reveal style={{ '--d': 2 }}>
          <div className="s-stage">
            <span className="s-stage__sheet s-stage__sheet--2" aria-hidden="true" />
            <span className="s-stage__sheet s-stage__sheet--1" aria-hidden="true" />
            <Tilt className="s-stage__front" max={3}>
              <Preview label="Preview of the student quiz screen: a multiple-choice question on paging with four options, a difficulty label, progress and a timer"
                path="Student portal  /  Assigned Quizzes">
                <QuizMock />
              </Preview>
            </Tilt>
            <div className="s-stage__chip">
              <Preview label="Preview of a topic mastery card" className="mk--small">
                <MasteryMock count={1} compact />
              </Preview>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* B — product in action */
const POINTS = [
  { icon: ClipboardList, text: 'Answers save as you go. Flag questions and jump between them.' },
  { icon: TrendingUp, text: 'After submitting, each topic shows a mastery estimate and the evidence behind it.' },
  { icon: Target, text: 'Fewer than 5 different questions on a topic shows Insufficient evidence, not a guess.' },
]

export function ProductInAction() {
  return (
    <section id="product" className="s-section s-section--white" aria-labelledby="product-title">
      <div className="s-wrap">
        <SectionHead id="product-title" eyebrow="Product in action" title="A quiz on one side. What it means on the other."
          lead="Students answer in a focused quiz player. When they submit, their topic mastery updates from the answers they gave." />
        <div className="s-pia">
          <div className="s-pia__main">
            <div data-reveal>
              <Preview label="Preview of the student quiz player with a question, the question navigator and the Submit quiz button"
                path="Student portal  /  Assigned Quizzes  /  Quiz 2" className="mk--wide">
                <PlayerMock />
              </Preview>
            </div>
            <ul className="s-points">
              {POINTS.map(({ icon: Icon, text }, i) => (
                <li key={text} data-reveal style={{ '--d': 3 + i }}>
                  <span className="s-points__icon"><Icon size={17} strokeWidth={1.8} aria-hidden="true" /></span>
                  {text}
                </li>
              ))}
            </ul>
          </div>
          <div className="s-pia__side">
            <div data-reveal style={{ '--d': 2 }}>
              <Preview label="Preview of two topic mastery cards from My Progress, with score, likely range, evidence and next step"
                path="Student portal  /  My Progress">
                <MasteryMock count={2} />
              </Preview>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* C — feature cards, each with its own layout */
export function Features() {
  return (
    <section id="features" className="s-section s-section--pale" aria-labelledby="features-title">
      <div className="s-wrap">
        <SectionHead id="features-title" eyebrow="Features" title="Three parts, built for coursework." />
        <div className="s-fgrid">
          <div className="s-fgrid__a" data-reveal>
            <Tilt className="s-fcard s-fcard--gen" max={3}>
              <div className="s-fcard__head">
                <span className="s-ficon"><ClipboardCheck size={20} strokeWidth={1.8} aria-hidden="true" /></span>
                <p className="s-fcard__who"><Presentation size={14} strokeWidth={1.8} aria-hidden="true" />Lecturers and students</p>
              </div>
              <h3>Quiz Generation</h3>
              <p>Turn topics or learning material into multiple-choice questions. Every question is checked for format and near-duplicates before anyone reviews it.</p>
              <div className="s-fcard__visual">
                <div className="s-gen__back">
                  <Preview label="Preview of the Create Quiz form: subject, topic, number of questions and difficulty" path="Lecturer portal  /  Create Quiz">
                    <CreateMock />
                  </Preview>
                </div>
                <div className="s-gen__front">
                  <Preview label="Preview of a finished generation run: five questions ready for review">
                    <GeneratedMock />
                  </Preview>
                </div>
              </div>
            </Tilt>
          </div>
          <div className="s-fgrid__b" data-reveal style={{ '--d': 1 }}>
            <Tilt className="s-fcard s-fcard--adapt" max={4}>
              <div className="s-fcard__split">
                <div>
                  <span className="s-ficon s-ficon--teal"><Target size={20} strokeWidth={1.8} aria-hidden="true" /></span>
                  <h3>Adaptive Practice</h3>
                  <p>Adjust practice difficulty using student performance and available evidence.</p>
                </div>
                <div className="s-fcard__visual">
                  <Preview label="Preview of next practice levels per topic with the reason for each" className="mk--flat">
                    <AdaptiveMock count={2} />
                  </Preview>
                </div>
              </div>
            </Tilt>
          </div>
          <div className="s-fgrid__c" data-reveal style={{ '--d': 2 }}>
            <Tilt className="s-fcard s-fcard--ana" max={4}>
              <div className="s-fcard__visual">
                <Preview label="Preview of mastery estimates for four Operating Systems topics" className="mk--flat">
                  <AnalyticsMock />
                </Preview>
              </div>
              <div className="s-fcard__foot">
                <span className="s-ficon s-ficon--navy"><ChartColumn size={20} strokeWidth={1.8} aria-hidden="true" /></span>
                <div>
                  <h3>Learning Analytics</h3>
                  <p>Understand topic mastery and identify areas that need revision.</p>
                </div>
              </div>
            </Tilt>
          </div>
        </div>
      </div>
    </section>
  )
}

/* D — lecturer and student */
const SIDES = [
  {
    key: 'lecturer', role: 'For lecturers', icon: Presentation,
    title: 'Review, approve, then see where the class stands.',
    items: [
      [FileCheck, 'Review each generated question with its answer key and automatic checks'],
      [CircleCheck, 'Publish only after every question is approved'],
      [ChartColumn, 'Inspect class mastery by student and topic'],
    ],
    visuals: [
      { label: 'Preview of a question waiting for review, and publishing locked until all questions are approved', path: 'Lecturer portal  /  Quizzes  /  Paging basics', Mock: ApprovalMock },
      { label: 'Preview of the class mastery heatmap of students by topic', path: 'Lecturer portal  /  Class Analytics', Mock: HeatmapMock },
    ],
  },
  {
    key: 'student', role: 'For students', icon: GraduationCap,
    title: 'Answer, track mastery, and know what to revise.',
    items: [
      [NotebookPen, 'Answer assigned quizzes or generate practice on any topic'],
      [TrendingUp, 'Track topic mastery with the evidence behind each estimate'],
      [CalendarClock, 'Revise missed questions on a spaced schedule'],
    ],
    visuals: [
      { label: 'Preview of next practice levels for weak topics', path: 'Student portal  /  Learning Insights', Mock: AdaptiveMock },
      { label: 'Preview of spaced revision with questions due now and upcoming', path: 'Student portal  /  Learning Insights', Mock: RevisionMock },
    ],
  },
]

export function Experience() {
  return (
    <section id="experience" className="s-section s-section--dark" aria-labelledby="exp-title">
      <div className="s-wrap">
        <SectionHead id="exp-title" eyebrow="Lecturers and students" title="Two sides of the same course."
          lead="Lecturers stay in control of what gets published. Students see what to work on next, with reasons." />
        <div className="s-sides">
          {SIDES.map(({ key, role, icon: Icon, title, items, visuals }, i) => (
            <article key={key} className={`s-side s-side--${key}`} data-reveal style={{ '--d': i }} aria-labelledby={`side-${key}`}>
              <p className="s-side__role"><span><Icon size={16} strokeWidth={1.8} aria-hidden="true" /></span>{role}</p>
              <h3 id={`side-${key}`}>{title}</h3>
              <ul className="s-side__list">
                {items.map(([ItemIcon, text]) => (
                  <li key={text}><ItemIcon size={16} strokeWidth={1.8} aria-hidden="true" />{text}</li>
                ))}
              </ul>
              <div className="s-side__visual">
                {visuals.map(({ label, path, Mock }, j) => (
                  <div key={label} className={`s-side__layer s-side__layer--${j + 1}`}>
                    <Preview label={label} path={path}><Mock /></Preview>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
        <p className="s-caption s-caption--dark">Previews use sample data.</p>
      </div>
    </section>
  )
}

/* E — how it works */
const STEPS = [
  { icon: BookOpen, title: 'Select a topic.', text: 'From a course syllabus, or any subject in Practice Lab.' },
  { icon: ListChecks, title: 'Generate or take a quiz.', text: 'Course quizzes reach students only after the lecturer approves every question.' },
  { icon: TrendingUp, title: 'Review results and improve.', text: 'See each topic’s mastery, weak areas and the next practice level.' },
]

export function HowItWorks() {
  return (
    <section id="how" className="s-section s-section--white s-section--tight" aria-labelledby="how-title">
      <div className="s-wrap">
        <SectionHead id="how-title" eyebrow="How it works" title="Three steps, every time." align="center" />
        <ol className="s-timeline">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="s-tstep" data-reveal style={{ '--d': i }}>
              <span className="s-tstep__node"><Icon size={20} strokeWidth={1.8} aria-hidden="true" /></span>
              <p className="s-tstep__n">Step {i + 1}</p>
              <h3>{title}</h3>
              <p>{text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

/* F — closing call to action */
export function ClosingCta() {
  return (
    <section className="s-final" aria-labelledby="cta-title">
      <div className="s-final__lines" aria-hidden="true" />
      <div className="s-wrap s-final__inner" data-reveal>
        <h2 id="cta-title">Make every practice session count.</h2>
        <p>Start building a clearer picture of what you know.</p>
        <Link className="s-btn s-btn--light" to="/register">Get Started<ArrowRight size={16} aria-hidden="true" /></Link>
      </div>
    </section>
  )
}
