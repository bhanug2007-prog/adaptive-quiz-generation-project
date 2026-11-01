import {
  Activity, BarChart3, CalendarDays, ClipboardList, FileBarChart, FileCheck2, FlaskConical, Gauge, GraduationCap, History,
  KeyRound, Lightbulb, Link2, ListChecks, RotateCcw, Rocket, Sparkles, TrendingUp, TriangleAlert, Users,
} from 'lucide-react'

/*
 * Content for the simple landing page. Every "how" sentence is written from the code:
 * backend/app/ml/*, backend/app/services/{adaptive_service,validation_service}.py,
 * docs/ML_EVALUATION.md, and the labels in src/layouts/nav.js and the portal pages.
 * Text inside [[double brackets]] is a real menu, tab or button label in the app.
 */

export const STUDENT_FEATURES = [
  {
    id: 'join',
    icon: KeyRound,
    title: 'Join a course with a code',
    what: 'Enrol in your lecturer’s course so its quizzes, subjects and topics show up for you.',
    how: 'Your lecturer shares a join code. Entering it adds you to the course roster. Your email must be verified first.',
    try: ['Open [[My Courses]].', 'Type the code into [[Join code]] and press [[Join course]].', 'The course appears with its subjects, units and topics.'],
  },
  {
    id: 'assigned',
    icon: ClipboardList,
    title: 'Assigned quizzes',
    what: 'Take the quizzes your lecturer published. Every question in them was approved by the lecturer.',
    how: 'Each answer is saved to the server as soon as you pick it, so after a refresh or a lost connection you carry on where you stopped. You can flag questions to come back to, and the submit dialog shows what is answered, unanswered and flagged.',
    try: ['Open [[Assigned Quizzes]] and press [[Start quiz]].', 'Answer a question, press [[Flag for review]], then refresh the page: your answer is still there.', 'Press [[Review and submit]], then [[Submit now]].'],
  },
  {
    id: 'practice',
    icon: FlaskConical,
    title: 'Practice quizzes',
    what: 'Make your own quiz on any topic, as often as you like. Practice scores are kept apart from assessment grades.',
    how: 'The AI model writes the questions and automatic checks screen them, but no lecturer reviews them, so they are labelled AI-generated and not lecturer-reviewed. With [[Adaptive]] difficulty the level comes from your mastery on that topic: a mix of levels while there is little evidence, then one level up after strong recent results or one down after weak ones, always with the reason shown.',
    try: ['Open [[Practice Lab]] and pick a topic.', 'Choose [[Adaptive]] under Difficulty and press [[Generate practice quiz]].', 'When it is ready, press [[Start the quiz]] and use [[Check answer]] as you go.'],
  },
  {
    id: 'results',
    icon: FileCheck2,
    title: 'Results and feedback',
    what: 'See your score, which answers were right, and an explanation for each question.',
    how: 'Correct, incorrect and skipped answers are counted separately, also per topic. Answers and explanations appear when your lecturer’s feedback setting allows: right after you submit, after the due date, or when the lecturer releases them.',
    try: ['Submit a quiz: the result page opens.', 'Later, open [[Quiz History]] and press [[Result]] on any attempt.'],
  },
  {
    id: 'progress',
    icon: TrendingUp,
    title: 'My Progress: mastery out of 100',
    what: 'An estimate, out of 100, of how well you know each topic, with the evidence behind it.',
    how: 'It is worked out from submitted answers only. Recent answers count more, a correct hard answer or a wrong easy one counts more, a repeated question counts half, and a skip counts as half a wrong answer. Each topic shows the evidence level, a trend (only when the change is clear; otherwise “No clear change”) and a next step. With fewer than 5 different questions it says “insufficient evidence” instead of a label.',
    try: ['Open [[My Progress]] and look at the topic mastery map.', 'Open [[How mastery is estimated]] to read the method.'],
  },
  {
    id: 'weak',
    icon: TriangleAlert,
    title: 'Weak areas',
    what: 'A short list of topics that need work.',
    how: 'A topic is listed when its estimate is “needs improvement”, or when a better estimate is clearly falling. Topics you have not tried are never called weak.',
    try: ['Open [[Learning Insights]] and read [[Weak areas]].'],
  },
  {
    id: 'recs',
    icon: Lightbulb,
    title: 'Recommendations',
    what: 'Up to 6 suggestions for what to do next, each with its reason.',
    how: 'They are rebuilt after every submitted quiz: practise a weak topic at the suggested level, fix a weak prerequisite topic first, or revisit questions you missed.',
    try: ['Open [[Learning Insights]], then [[Recommendations]].', 'Press [[Practise]] to open the Practice Lab already filled in, or [[Done]] when finished.'],
  },
  {
    id: 'revision',
    icon: RotateCcw,
    title: 'Spaced revision',
    what: 'Questions you missed come back for review on a schedule.',
    how: 'A missed or skipped question is scheduled again after 1 day, then 3, 7, 14 and 30 days as you get it right. A wrong answer sends it back to the start. A revision quiz takes up to 10 due questions.',
    try: ['Open [[Learning Insights]], find [[Spaced revision]] and press [[Start revision]] when questions are due.'],
  },
  {
    id: 'confidence',
    icon: Gauge,
    title: 'Confidence calibration',
    what: 'Shows whether how sure you feel matches how often you are right.',
    how: 'In a practice quiz you can rate how sure you are before checking each answer. After 10 rated answers, with at least 3 at each level, the app shows the pattern.',
    try: ['In [[Practice Lab]], tick [[Ask me how confident I am before checking each answer]].', 'Rate each answer under [[How sure are you?]].', 'Open [[Learning Insights]], then [[Confidence calibration]].'],
  },
  {
    id: 'plan',
    icon: CalendarDays,
    title: 'Study plan',
    what: 'A plan for this week: which topics to work on, why, and for how long.',
    how: 'It is built from your mastery and from assessments due within the next 7 days. If you enter your weekly study hours, the time is split between the topics.',
    try: ['Open [[Profile]], fill in [[Weekly study hours]] and press [[Save changes]].', "Open [[Learning Insights]] and read [[This week's study plan]]."],
  },
  {
    id: 'history',
    icon: History,
    title: 'Quiz history',
    what: 'Every attempt you have started, assessments and practice together or apart.',
    how: 'Each row shows the score and the correct, incorrect and skipped counts. An unfinished attempt can be resumed from here.',
    try: ['Open [[Quiz History]] and switch [[Show]] between [[All]], [[Assessments]] and [[Practice]].'],
  },
]

export const LECTURER_FEATURES = [
  {
    id: 'courses',
    icon: GraduationCap,
    title: 'Courses, subjects, units, topics and the join code',
    what: 'Set up your course the way the syllabus is laid out. Quizzes and analytics are organised by it.',
    how: 'A course holds subjects, a subject holds units, a unit holds topics, and each topic can have learning objectives. Every course gets a join code you can copy, replace or switch off. You can also enrol students by email.',
    try: ['Open [[Courses & Subjects]] and press [[New course]].', 'Open the course, press [[Add subject]], then use [[Add unit]], [[Add topic]] and [[Add objective]].', 'Press [[Copy]] next to the join code and share it with your class.'],
  },
  {
    id: 'generate',
    icon: Sparkles,
    title: 'AI quiz generation with automatic checks',
    what: 'Pick a topic and settings, and the AI model drafts the questions for you.',
    how: 'Questions are written one at a time. Each one is checked automatically: 4 distinct options with one answer, no near-duplicate wording, the stem does not give the answer away, enough of its words come from your reference material when you give some, and numeric answers are re-calculated in a locked-down Python process (in Docker or on Linux; on Windows that check is skipped and left to your review). A question that fails is retried, up to 3 attempts. Live progress shows how many are ready, and you can leave the page and come back.',
    try: ['Open [[Create Quiz]] and choose the course, subject, unit and topic.', 'Set the number of questions and difficulty, then press [[Generate questions]].', 'When it finishes, press the [[Review]] button (it shows how many questions passed) to open the drafts.'],
  },
  {
    id: 'review',
    icon: ListChecks,
    title: 'Review: approve, edit, reject, regenerate',
    what: 'Check every question before students can see it.',
    how: 'You can approve, edit, reject with a note, or ask the model for a replacement on the same topic and difficulty. Editing an approved question sends it back for approval. Once students have answered a question it is locked, so past results stay correct.',
    try: ['Open [[Quizzes]] and open the draft.', 'On the [[Questions]] tab use [[Approve]], [[Edit]], [[Reject]] or [[Regenerate]] on each question.', 'Every question you generate or write is also kept in [[Question Bank]], with its review status.'],
  },
  {
    id: 'publish',
    icon: Rocket,
    title: 'Quiz settings and publishing',
    what: 'Decide marks, timing, attempts, feedback and grade weight, then publish.',
    how: 'Choose graded or practice only, attempts, time limit, open and due dates, late penalty, when students see answers, shuffling, and the contribution to the subject grade. The graded quizzes of a subject cannot add up to more than its quiz weight cap; the server refuses it. Publishing only unlocks when every question is approved.',
    try: ['In the quiz, on the [[Settings]] tab, fill in the form and press [[Save settings]].', 'On [[Preview & publish]], check the student preview and press [[Publish to students]].'],
  },
  {
    id: 'analytics',
    icon: BarChart3,
    title: 'Class analytics and mastery heatmap',
    what: 'See how the class is doing and where the gaps are.',
    how: 'Every number comes from submitted attempts: class average, completion, skipped answers, score distribution, accuracy by difficulty, commonly missed questions and students who may need support. The heatmap shows each student’s mastery per topic, with “insufficient evidence” and “not attempted” kept apart from weak.',
    try: ['Open [[Class Analytics]] and switch between [[Class performance]], [[Mastery heatmap]] and [[Insights & coverage]].'],
  },
  {
    id: 'qanalytics',
    icon: ClipboardList,
    title: 'Question analytics',
    what: 'Find questions that are too easy, too hard or confusing.',
    how: 'For each question: answers, correct, incorrect and skipped, average time, and how well it separates stronger from weaker students. Review signals only appear once a question has 10 answers.',
    try: ['Open [[Question Analytics]], stay on [[Question quality]] and pick a quiz.'],
  },
  {
    id: 'profiles',
    icon: Users,
    title: 'Student profiles',
    what: 'One page per student in your courses.',
    how: 'Shows topic mastery with its evidence, the student’s attempts on your quizzes, topics recommended for revision, repeated mistakes and skipped questions.',
    try: ['Open [[Students]] and choose a student.'],
  },
  {
    id: 'reports',
    icon: FileBarChart,
    title: 'Reports, CSV and manual export',
    what: 'Download results, or copy a quiz into another system.',
    how: 'CSV files of student-wise marks, topic-wise performance and per-quiz results open in Excel or Google Sheets. The manual export is plain text with questions, options, answer key and explanations, for a fully approved quiz.',
    try: ['Open [[Reports]] and press [[CSV]] on a report.', 'In a quiz, open [[Reports & export]] and press [[Show export text]], then [[Copy to clipboard]].'],
  },
  {
    id: 'model',
    icon: Activity,
    title: 'Model evaluation tab',
    what: 'See how the question-writing model has performed for you.',
    how: 'Reliability from the automatic checks (pass rate, retry rate, time per question and why outputs were rejected) next to your own review decisions (approval, rejection and edit rates). Small samples are marked as such.',
    try: ['Open [[Question Analytics]] and switch to [[Model evaluation]].'],
  },
  {
    id: 'forms',
    icon: Link2,
    title: 'Google Forms export',
    what: 'Turn a fully approved quiz into a Google Form in your own Google account.',
    how: 'It only works when the server has been set up for Google. Note: this integration has not yet been tested against the live Google Forms API, so check every form it creates. The manual export always works.',
    try: ['Open [[Settings]] in the side menu and press [[Connect Google account]].', 'In a quiz, open [[Reports & export]] and press [[Create Google Form]].'],
    note: 'Not yet tested with Google',
  },
]

export const HOW_STEPS = [
  { title: 'The lecturer builds the course', text: 'Course, subjects, units and topics, then shares the join code. Students join with it.' },
  { title: 'The AI drafts, the lecturer reviews', text: 'The model writes questions for a topic, the automatic checks screen them, and the lecturer approves, edits or rejects each one.' },
  { title: 'The lecturer publishes', text: 'Marks, dates, attempts, feedback and grade weight are set, and the quiz goes to enrolled students.' },
  { title: 'Students take quizzes', text: 'Assigned quizzes and their own practice quizzes. Answers save as they go.' },
  { title: 'Both sides see what changed', text: 'Each submitted quiz updates mastery, weak areas, recommendations, practice difficulty and revision. Students see it in My Progress; lecturers in Class Analytics.' },
]

export const TRY_LECTURER = [
  'Press [[Get started]], choose [[Lecturer]] under [[I am a]], and enter the [[Lecturer invite code]] your administrator gives you. Press [[Create account]].',
  'Open the verification link sent to your email. Generating and publishing need a verified email.',
  'In [[Courses & Subjects]], create a course with one subject, unit and topic. Copy the join code.',
  'In [[Create Quiz]], pick the topic and press [[Generate questions]]. Review and approve every question.',
  'Save the quiz settings and press [[Publish to students]].',
  'Once students submit, open [[Class Analytics]], [[Question Analytics]] and [[Students]].',
]

export const TRY_STUDENT = [
  'Press [[Get started]], keep [[Student]] selected, fill in the form and press [[Create account]]. Verify your email.',
  'In [[My Courses]], enter the join code from your lecturer and press [[Join course]].',
  'In [[Assigned Quizzes]], start a quiz. Flag one question, refresh the page to see your answers kept, then submit.',
  'Read your result, then open [[My Progress]]. A topic gets a label once you have answered 5 different questions on it.',
  'In [[Practice Lab]], generate an [[Adaptive]] practice quiz and check your answers as you go.',
  'Open [[Learning Insights]] for weak areas, recommendations, spaced revision and your study plan.',
]
