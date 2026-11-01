import {
  BarChart3, BookOpen, ClipboardList, FileBarChart, FlaskConical, GraduationCap, History, LayoutDashboard, Library,
  Lightbulb, ListChecks, PlusCircle, Settings, TrendingUp, User, Users,
} from 'lucide-react'

export const STUDENT_NAV = [
  { to: '/student', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/student/courses', label: 'My Courses', icon: BookOpen },
  { to: '/student/assigned', label: 'Assigned Quizzes', icon: ClipboardList },
  { to: '/student/practice', label: 'Practice Lab', icon: FlaskConical },
  { to: '/student/progress', label: 'My Progress', icon: TrendingUp },
  { to: '/student/insights', label: 'Learning Insights', icon: Lightbulb },
  { to: '/student/history', label: 'Quiz History', icon: History },
  { to: '/student/profile', label: 'Profile', icon: User },
]

export const LECTURER_NAV = [
  { to: '/lecturer', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/lecturer/courses', label: 'Courses & Subjects', icon: GraduationCap },
  { to: '/lecturer/questions', label: 'Question Bank', icon: Library },
  { to: '/lecturer/create', label: 'Create Quiz', icon: PlusCircle },
  { to: '/lecturer/quizzes', label: 'Quizzes', icon: ListChecks },
  { to: '/lecturer/students', label: 'Students', icon: Users },
  { to: '/lecturer/analytics', label: 'Class Analytics', icon: BarChart3 },
  { to: '/lecturer/question-analytics', label: 'Question Analytics', icon: ClipboardList },
  { to: '/lecturer/reports', label: 'Reports', icon: FileBarChart },
  { to: '/lecturer/settings', label: 'Settings', icon: Settings },
]
