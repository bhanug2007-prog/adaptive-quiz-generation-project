import { useEffect } from 'react'
import { GraduationCap } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Button, EmptyState, ErrorState, Field, LoadingBlock, Select } from '../ui'
import { rememberCourse, rememberedCourse } from './util'

/**
 * Loads the lecturer's courses and lets them choose one. Renders loading / error / empty states itself;
 * calls children(courses) once there is at least one course.
 */
export function useCourses() {
  return useApi(() => lecturerApi.courses(), [])
}

export function CourseGate({ courses, children, emptyText = 'Create a course first. Its analytics appear here once students submit quizzes.' }) {
  if (courses.loading) return <LoadingBlock rows={3} label="Loading courses" />
  if (courses.error) return <ErrorState error={courses.error} onRetry={courses.reload} />
  const list = (courses.data || []).filter((c) => !c.archived)
  if (!list.length) {
    return (
      <EmptyState icon={GraduationCap} title="No courses yet" action={<Button variant="primary" to="/lecturer/courses">Create a course</Button>}>
        {emptyText}
      </EmptyState>
    )
  }
  return children(list)
}

/** Controlled course select. Picks the remembered (or first) course when value is empty. */
export function CourseSelect({ courses, value, onChange, label = 'Course', allowAll }) {
  useEffect(() => {
    if (value || allowAll || !courses.length) return
    const r = rememberedCourse()
    const pick = courses.find((c) => String(c.id) === r) || courses[0]
    onChange(String(pick.id))
  }, [value, courses, onChange, allowAll])
  return (
    <Field label={label}>
      {(a) => (
        <Select {...a} value={value || ''} onChange={(e) => { rememberCourse(e.target.value); onChange(e.target.value) }}>
          {allowAll && <option value="">All courses</option>}
          {courses.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.title}</option>)}
        </Select>
      )}
    </Field>
  )
}
