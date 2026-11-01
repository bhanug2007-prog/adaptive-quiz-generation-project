import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import RequireRole from '../auth/RequireRole'
import PortalLayout from '../layouts/PortalLayout'
import PublicLayout from '../layouts/PublicLayout'
import { LoadingBlock } from '../components/ui'
import RouteErrorBoundary from './RouteErrorBoundary'

const Landing = lazy(() => import('../pages/landing/Landing'))
const SignIn = lazy(() => import('../pages/auth/SignIn'))
const Register = lazy(() => import('../pages/auth/Register'))
const VerifyEmail = lazy(() => import('../pages/auth/VerifyEmail'))
const NotFound = lazy(() => import('../pages/NotFound'))

const S = {
  Overview: lazy(() => import('../pages/student/Overview')),
  Courses: lazy(() => import('../pages/student/Courses')),
  Assigned: lazy(() => import('../pages/student/Assigned')),
  Practice: lazy(() => import('../pages/student/Practice')),
  QuizIntro: lazy(() => import('../pages/student/QuizIntro')),
  Player: lazy(() => import('../pages/student/QuizPlayer')),
  Result: lazy(() => import('../pages/student/Result')),
  Progress: lazy(() => import('../pages/student/Progress')),
  Insights: lazy(() => import('../pages/student/Insights')),
  History: lazy(() => import('../pages/student/History')),
  Profile: lazy(() => import('../pages/student/Profile')),
}

const L = {
  Overview: lazy(() => import('../pages/lecturer/Overview')),
  Courses: lazy(() => import('../pages/lecturer/Courses')),
  CourseDetail: lazy(() => import('../pages/lecturer/CourseDetail')),
  QuestionBank: lazy(() => import('../pages/lecturer/QuestionBank')),
  CreateQuiz: lazy(() => import('../pages/lecturer/CreateQuiz')),
  Quizzes: lazy(() => import('../pages/lecturer/Quizzes')),
  QuizDetail: lazy(() => import('../pages/lecturer/QuizDetail')),
  Students: lazy(() => import('../pages/lecturer/Students')),
  StudentProfile: lazy(() => import('../pages/lecturer/StudentProfile')),
  ClassAnalytics: lazy(() => import('../pages/lecturer/ClassAnalytics')),
  QuestionAnalytics: lazy(() => import('../pages/lecturer/QuestionAnalytics')),
  Reports: lazy(() => import('../pages/lecturer/Reports')),
  Settings: lazy(() => import('../pages/lecturer/Settings')),
}

const Page = ({ children }) => (
  <RouteErrorBoundary>
    <Suspense fallback={<LoadingBlock />}>{children}</Suspense>
  </RouteErrorBoundary>
)

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route index element={<Page><Landing /></Page>} />
      </Route>
      <Route path="signin" element={<Page><SignIn /></Page>} />
      <Route path="register" element={<Page><Register /></Page>} />
      <Route path="verify-email" element={<Page><VerifyEmail /></Page>} />

      <Route path="student" element={<RequireRole role="student" />}>
        <Route element={<PortalLayout role="student" />}>
          <Route index element={<Page><S.Overview /></Page>} />
          <Route path="courses" element={<Page><S.Courses /></Page>} />
          <Route path="assigned" element={<Page><S.Assigned /></Page>} />
          <Route path="practice" element={<Page><S.Practice /></Page>} />
          <Route path="quizzes/:quizId" element={<Page><S.QuizIntro /></Page>} />
          <Route path="attempts/:sessionId" element={<Page><S.Player /></Page>} />
          <Route path="attempts/:sessionId/result" element={<Page><S.Result /></Page>} />
          <Route path="progress" element={<Page><S.Progress /></Page>} />
          <Route path="insights" element={<Page><S.Insights /></Page>} />
          <Route path="history" element={<Page><S.History /></Page>} />
          <Route path="profile" element={<Page><S.Profile /></Page>} />
          <Route path="*" element={<Page><NotFound /></Page>} />
        </Route>
      </Route>

      <Route path="lecturer" element={<RequireRole role="lecturer" />}>
        <Route element={<PortalLayout role="lecturer" />}>
          <Route index element={<Page><L.Overview /></Page>} />
          <Route path="courses" element={<Page><L.Courses /></Page>} />
          <Route path="courses/:courseId" element={<Page><L.CourseDetail /></Page>} />
          <Route path="questions" element={<Page><L.QuestionBank /></Page>} />
          <Route path="create" element={<Page><L.CreateQuiz /></Page>} />
          <Route path="quizzes" element={<Page><L.Quizzes /></Page>} />
          <Route path="quizzes/:quizId" element={<Page><L.QuizDetail /></Page>} />
          <Route path="students" element={<Page><L.Students /></Page>} />
          <Route path="students/:studentId" element={<Page><L.StudentProfile /></Page>} />
          <Route path="analytics" element={<Page><L.ClassAnalytics /></Page>} />
          <Route path="question-analytics" element={<Page><L.QuestionAnalytics /></Page>} />
          <Route path="reports" element={<Page><L.Reports /></Page>} />
          <Route path="settings" element={<Page><L.Settings /></Page>} />
          <Route path="*" element={<Page><NotFound /></Page>} />
        </Route>
      </Route>

      <Route element={<PublicLayout />}>
        <Route path="*" element={<Page><NotFound /></Page>} />
      </Route>
    </Routes>
  )
}
