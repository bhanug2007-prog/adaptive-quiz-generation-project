# AdaptiveIQ

### AI-assisted assessment and personalized learning

AdaptiveIQ is a full-stack assessment and personalized learning platform. Lecturers turn study material into reviewed quizzes, see which students left the quiz window during monitored attempts, and find topics the class struggled with. Students take quizzes, see their topic-level progress, and approve personalized practice plans that they can resume later.

**Individual project** · Python · FastAPI · React · PostgreSQL · Qwen2.5-7B · LangGraph

[Architecture](adaptiveiq/docs/ARCHITECTURE.md) · [Local setup](adaptiveiq/README.md) · [Training notebook](code/finetune_qwen7b_unsloth.ipynb) · [Evaluation](adaptiveiq/docs/ML_EVALUATION.md) · [API reference](adaptiveiq/docs/API.md)

**[Open the live AdaptiveIQ demo](https://adaptiveiq-demo.onrender.com)**

## Table of Contents

- [Live Demo](#live-demo)
- [Problem Statement](#problem-statement)
- [Proposed Solution](#proposed-solution)
- [Key Features and User Roles](#key-features-and-user-roles)
- [How an Assessment Works](#how-an-assessment-works)
- [Quiz Monitoring and Lecturer Review](#quiz-monitoring-and-lecturer-review)
- [LangGraph and Adaptive Practice](#langgraph-and-adaptive-practice)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Model Engineering](#model-engineering)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Validation and Testing](#validation-and-testing)
- [Deployment Notes](#deployment-notes)
- [Known Limitations](#known-limitations)

## Live Demo

### Try the lecturer and student workflows

1. Open the live demo and click **Get started** to sign up.
2. Under **I am a**, select **Lecturer**. Enter `AdaptiveIQ-Demo-Local-Only` in the **Lecturer invite code** field, then click **Create account**.
3. Create a demo course and topic, then open **Create a quiz**. Generate and review one question. In **Settings**, enable **Integrity monitoring** and turn on recording when students leave the quiz page, then publish the quiz.
4. In a separate browser profile or incognito window, register as a **Student** and join the course using its join code. Start the quiz after reading the monitoring notice, switch tabs briefly, return, and submit.
5. Back in the lecturer account, open **Quiz → Monitoring → Timeline** for that student's attempt. In the student account, explore **Learning Insights** to see topic evidence and the practice plan workflow. A single question gives you only a small amount of mastery evidence.

This is a shared portfolio demo. Use sample course names and reference material.

The first visit after inactivity may take about a minute while Render starts. Live generation is subject to the Hugging Face Space's GPU quota.

## Problem Statement

Lecturers spend time turning course material into quiz questions, checking answers, and judging difficulty. During a remote assessment, they also have limited visibility into when a student leaves the quiz page. After submission, a total score gives students little guidance on which concepts to practice next. AdaptiveIQ connects quiz preparation, attempt review, and follow-up practice in the same course.

## Proposed Solution

**For lecturers**, AdaptiveIQ drafts multiple-choice questions from a topic or uploaded study material. It checks question format, duplicates, and supported mathematical answers. Lecturers can edit, approve, or reject drafts before publishing a quiz.

**For students**, AdaptiveIQ uses quiz attempts to update mastery by topic. It recommends what to practice next based on weaker topics, appropriate difficulty, and when a topic is due for review. Lecturers can also use class analytics to see which topics need more attention.

For example, a data structures lecturer can create a quiz from notes on searching and sorting. A student who answers sorting questions correctly but misses binary-search questions can get a targeted recommendation to practice binary search.

## Key Features and User Roles

| Role | What you can do |
| --- | --- |
| **Lecturer** | Create courses and topics, invite students with a join code, generate questions from topics or PDF/DOCX/TXT material, edit and approve drafts, and publish quizzes. Review monitored attempts, question performance, and class results by topic. |
| **Student** | Join a course, complete assigned quizzes, and view scores and topic-level progress. Review and approve steps in a personalized practice plan, then return later to continue. |

## How an Assessment Works

1. A lecturer chooses a topic or uploads study material and requests a difficulty mix.
2. The **Question Quality Agent** coordinates draft generation, automated checks, and bounded retries. The lecturer reviews and publishes the assessment.
3. Students join the course and answer the quiz. If monitoring is enabled, activity events are recorded for lecturer review.
4. FastAPI scores attempts and updates the evidence behind student and class analytics. The read-only **Lecturer Insights Agent** uses anonymized tool results to answer questions about class performance, with optional AI wording.
5. Topic mastery and revision policies inform the next practice recommendation or a student-approved learning plan.

## Quiz Monitoring and Lecturer Review

Lecturers can enable monitoring per assigned quiz. Before starting, the student sees what will be recorded and agrees to it. Practice quizzes run without monitoring.

- **Tab and window changes.** If the quiz tab becomes hidden or the quiz window loses focus, AdaptiveIQ records the departure and return. For example, switching to another tab or browser window can create a timeline entry with the time and duration.
- **Fullscreen, camera, and microphone.** Lecturers can record fullscreen exits and optionally enable camera or microphone signals. MediaPipe counts faces in the student's browser, and Web Audio measures speech-like activity there. The server receives event metadata such as timestamps, durations, and face counts. Images, video, and audio stay on the device.
- **Per-student timeline.** The lecturer who owns the quiz can open **Monitoring**, see which student's attempt recorded events, inspect the timeline, and mark it for follow-up or record no concern. Thresholds help prioritize review. The browser cannot identify which website or application the student opened, and monitoring events do not automatically change marks.

[Monitoring design and tests](adaptiveiq/docs/MONITORING.md)

## LangGraph and Adaptive Practice

I used **LangGraph** to manage the student practice workflow across visits. After a student submits a quiz, FastAPI scores the attempt and the adaptive engine updates topic mastery using weighted Beta–Bernoulli estimation. The learning graph uses that evidence, difficulty rules, and spaced revision to propose a practice plan and explain the recommended steps.

1. **Build the plan.** Choose practice actions from the student's topic evidence and revision schedule.
2. **Pause for approval.** Save the plan to a SQLAlchemy-backed checkpoint so the student can leave and return later.
3. **Resume and hand off.** When the student approves a step, resume the workflow, recheck access, and hand the approved action to the practice service. When the action calls for a new quiz, Qwen generates the questions.

The mastery and planning rules are deterministic. Qwen handles question generation, and LangGraph handles the plan's state, approval, and handoff. [Learning workflow diagram](adaptiveiq/docs/ARCHITECTURE.md#learning-feedback-and-persistent-plans) · [LangGraph implementation](adaptiveiq/backend/app/agents/personalized_learning.py)

## Technology Stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | React, Vite, JavaScript | Lecturer and student portals, quiz player, and dashboards |
| Backend | Python, FastAPI | REST API, quiz scoring, access checks, and generation queue |
| Data | PostgreSQL, SQLite, SQLAlchemy, Alembic | Application records, local development, migrations, and learning-plan checkpoints |
| Model | Qwen2.5-7B, PyTorch, Unsloth, LoRA, llama.cpp | Fine-tuning, evaluation, and local GGUF inference |
| Learning | LangGraph, weighted Beta–Bernoulli mastery | Practice recommendations, approval, and resumable plans |
| Monitoring | Page Visibility API, window focus events, MediaPipe, Web Audio | Browser-side activity detection and attempt events |
| Testing and deployment | pytest, Vitest, Playwright, Docker, Render, Hugging Face ZeroGPU | Automated verification, cloud app hosting, and hosted inference |

## Architecture

The backend coordinates assessment and learning workflows. Qwen generates content, and the adaptive engine computes mastery and recommendations. The diagram shows the local llama.cpp inference path. The live demo calls the Hugging Face ZeroGPU Space from the same backend model service.

```mermaid
flowchart TB
    subgraph browser["Browser · React + Vite"]
        UI["Lecturer and student portals"]
        Signals["MediaPipe + Web Audio<br/>Consented activity signals"]
    end
    subgraph backend["Application server · FastAPI"]
        API["API boundary<br/>Authentication · roles · ownership checks"]
        Generation["Document extraction + question pipeline<br/>Validation · retries · lecturer review"]
        Assessment["Quizzes + attempts<br/>Scoring · results · analytics"]
        Adaptive["Explainable adaptive engine<br/>Mastery · difficulty · spaced revision"]
        Learning["LangGraph learning workflow<br/>Plan · approval · resume · quiz handoff"]
        Insights["Lecturer insights<br/>Read-only analytics tools"]
        Monitor["Monitoring service<br/>Events · warnings · review"]
    end
    DB[("PostgreSQL / local SQLite<br/>SQLAlchemy + Alembic<br/>Application data + checkpoints")]
    Qwen["llama.cpp model server<br/>Fine-tuned Qwen2.5-7B · GGUF"]
    Reviewer["Optional external AI provider<br/>Question review + insights wording"]
    UI -->|"HTTP /api"| API
    Signals -->|"Event metadata"| API
    API --> Generation
    API --> Assessment
    API --> Learning
    API --> Insights
    API --> Monitor
    Generation -->|"OpenAI-compatible requests"| Qwen
    Generation -.-> Reviewer
    Insights -.-> Reviewer
    Assessment --> Adaptive
    Learning --> Adaptive
    Learning -->|"Approved practice action"| Generation
    Generation --> DB
    Assessment --> DB
    Learning --> DB
    Insights --> DB
    Monitor --> DB
    classDef client fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef service fill:#eef2ff,stroke:#6366f1,color:#312e81
    classDef external fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef data fill:#dcfce7,stroke:#16a34a,color:#14532d
    class UI,Signals client
    class API,Generation,Assessment,Adaptive,Learning,Insights,Monitor service
    class Qwen,Reviewer external
    class DB data
```

Solid arrows show application data and control flow; dashed arrows show optional AI calls. Browser monitoring sends metadata, not raw media. External AI review receives question content and selected source passages; insights use anonymized analytics. SMTP and optional Google Forms integration are described in the [architecture reference](adaptiveiq/docs/ARCHITECTURE.md).

## Model Engineering

```mermaid
flowchart LR
    Data["MCQ dataset<br/>Train / validation / test splits"] --> Train["Qwen2.5-7B-Instruct<br/>LoRA / QLoRA training"]
    Train --> Merge["Merge adapter<br/>Convert and quantize to GGUF"]
    Merge --> Serve["llama.cpp<br/>OpenAI-compatible API"]
    Serve --> App["AdaptiveIQ<br/>Generate · validate · review"]
```

- **Training:** [Qwen fine-tuning notebook](code/finetune_qwen7b_unsloth.ipynb), using Unsloth and LoRA adapters.
- **Inference:** [GGUF conversion notebook](code/convert_7b_to_gguf_kaggle.ipynb) and a separate llama.cpp server, keeping model weights outside the web API process.
- **Evaluation:** [Committed experiment results](results/) and an [evaluation guide](adaptiveiq/docs/ML_EVALUATION.md) covering generation quality, base-versus-fine-tuned comparisons, and adaptive-engine simulations.

The preliminary 30-item, AI-assisted pilot does **not** establish that fine-tuning outperforms the base 7B model. A controlled, blind human evaluation remains future work. Adaptive-learning results use synthetic students, not a real classroom study.

## Project Structure

```text
adaptiveiq/                    Full-stack application
  backend/                     FastAPI, learning policies, migrations and tests
  frontend/                    React portals, monitoring and browser tests
  docs/                        Architecture, API, evaluation and deployment guides
    verification/              Dated integration and feature checks
  deploy/                      Model-hosting configuration
code/                          Training, conversion and evaluation notebooks
results/                       Committed experiment outputs
btech_mcq_dataset_clean.zip     Dataset archive used by the experiments
PUBLISHING.md                  Future update and deployment workflow
```

Start with the [experiment guide](code/README.md) for the model work or the [results guide](results/README.md) for evaluation evidence. Runtime logs, credentials, local databases, dependencies and model weights are ignored.

## Explore the implementation

| Area | Source |
| --- | --- |
| API and application services | [Routes](adaptiveiq/backend/app/api/) · [Services](adaptiveiq/backend/app/services/) |
| Explainable learning policies | [Adaptive engine](adaptiveiq/backend/app/ml/) |
| Agent workflows and persistence | [Agents](adaptiveiq/backend/app/agents/) |
| Student and lecturer interfaces | [React frontend](adaptiveiq/frontend/src/) |
| Database evolution | [Alembic migrations](adaptiveiq/backend/alembic/versions/) |
| Automated verification | [Backend tests](adaptiveiq/backend/tests/) · [Frontend tests and components](adaptiveiq/frontend/src/components/) · [Browser tests](adaptiveiq/frontend/e2e/) |
| Training and experiments | [Notebooks and scripts](code/) · [Results](results/) |

## Getting Started

Start with the [application setup guide](adaptiveiq/README.md). The supplied Windows scripts expect Python 3.11+ and Node.js 22.12+; PostgreSQL is recommended, with SQLite available for local development.

```powershell
git clone https://github.com/bhanug2007-prog/adaptive-quiz-generation-project.git
cd adaptive-quiz-generation-projectdaptiveiq
.\setup_windows.bat
.\start_windows.bat
```

For generation, supply the GGUF model and llama.cpp executable as described in the setup guide, or configure a compatible model endpoint. The website runs at `http://localhost:5173` and the API at `http://localhost:8000` with the default local configuration. Test fixtures support development without the real model.

## Validation and Testing

The repository includes pytest, Vitest, and Playwright suites for API behavior, learning policies, permissions, UI flows, and monitoring. Historical verification is documented in the [QA report](adaptiveiq/docs/QA_REPORT.md), [Groq integration report](adaptiveiq/docs/verification/GROQ_REVIEW_VERIFICATION.md), and [activity-warning report](adaptiveiq/docs/verification/ACTIVITY_WARNINGS_VERIFICATION.md); these are dated records, not live CI status.

## Deployment Notes

The live demo serves React and FastAPI from a single Render web service backed by PostgreSQL. FastAPI calls Hugging Face ZeroGPU for Qwen inference. The repository includes the [Render Blueprint](render.yaml), [Space app](adaptiveiq/deploy/huggingface/app.py), and [deployment guide](adaptiveiq/docs/DEPLOYMENT.md). Supply model weights separately when running inference locally.

## Known Limitations

- LLM-generated questions still require review; mathematical and AI checks are not guarantees of correctness.
- CPU generation can be slow. Hosting the 7B model requires separate compute planning.
- Monitoring signals support lecturer review and do not establish misconduct.
- Document extraction supports text-based PDFs; scanned documents require OCR, which is not implemented.
- Google Forms integration requires environment-specific validation.

## Documentation

[Setup and tests](adaptiveiq/README.md) · [Architecture](adaptiveiq/docs/ARCHITECTURE.md) · [API](adaptiveiq/docs/API.md) · [Evaluation](adaptiveiq/docs/ML_EVALUATION.md) · [Monitoring](adaptiveiq/docs/MONITORING.md) · [Deployment](adaptiveiq/docs/DEPLOYMENT.md) · [Publishing future updates](PUBLISHING.md)

