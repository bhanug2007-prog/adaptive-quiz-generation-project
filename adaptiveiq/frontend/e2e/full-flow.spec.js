// Full flow in a real browser against a real backend (empty SQLite, TEST-ONLY fake model, invite code dev-invite):
// a lecturer builds a course, generates, reviews and publishes a quiz; a student joins, takes it and sees the result.
import { expect, test } from '@playwright/test'

const stamp = Date.now()
const lecturer = { name: 'E2E Lecturer', email: `lect${stamp}@example.com` }
const student = { name: 'E2E Student', email: `stud${stamp}@example.com` }
const PASSWORD = 'Passw0rd1'
const shared = {}

async function register(page, who, role) {
  await page.goto('/register')
  if (role === 'lecturer') await page.getByRole('radiogroup', { name: 'Account type' }).getByText('Lecturer').click()
  await page.getByLabel('Full name').fill(who.name)
  await page.getByLabel('Email').fill(who.email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByLabel('Confirm password').fill(PASSWORD)
  if (role === 'lecturer') await page.getByLabel('Lecturer invite code').fill('dev-invite')
  await page.getByRole('button', { name: 'Create account' }).click()
  await page.waitForURL(new RegExp(`/${role}`))
}

function watchErrors(page) {
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => {
    // 401 before sign-in and the deliberate 4xx responses are expected; anything else is a bug.
    if (m.type() === 'error' && !/status of 4\d\d/.test(m.text())) errors.push(m.text())
  })
  return errors
}

test.describe.serial('AdaptiveIQ full flow', () => {
  test('lecturer builds, reviews and publishes a quiz', async ({ page }) => {
    const errors = watchErrors(page)
    await register(page, lecturer, 'lecturer')
    const dlg = page.locator('dialog[open]')

    await page.goto('/lecturer/courses')
    await page.getByRole('button', { name: 'New course' }).click()
    await dlg.getByLabel('Course code').fill(`E2E${stamp % 1000}`)
    await dlg.getByLabel('Title').fill('Operating Systems E2E')
    await dlg.getByRole('button', { name: 'Create course' }).click()
    await page.waitForURL(/\/lecturer\/courses\/\d+/)
    const courseId = page.url().split('/').pop()
    shared.joinCode = (await page.locator('.lc-code--lg').textContent()).trim()
    expect(shared.joinCode).toMatch(/\S{4,}/)

    await page.getByRole('button', { name: 'Add subject' }).first().click()
    await dlg.getByLabel('Subject name').fill('Operating Systems')
    await dlg.getByLabel(/Quiz weight cap/).fill('20')
    await dlg.getByRole('button', { name: 'Add subject' }).click()
    await page.getByLabel('Add unit').fill('Unit 1: Processes')
    await page.getByRole('button', { name: 'Add unit' }).click()
    await page.getByRole('button', { name: 'Add topic' }).click()
    await dlg.getByLabel('Topic name').fill('CPU scheduling')
    await dlg.getByRole('button', { name: 'Add topic' }).click()
    await expect(page.getByText('CPU scheduling').first()).toBeVisible()

    await page.goto('/lecturer/create')
    await page.getByLabel('Course', { exact: true }).selectOption(courseId)
    await page.getByLabel('Quiz title').fill('Scheduling quiz E2E')
    await page.getByLabel('Number of questions').fill('3')
    await page.getByRole('button', { name: 'Generate questions' }).click()
    await page.getByRole('button', { name: /Review \d+ questions/ }).click({ timeout: 90_000 })
    await page.waitForURL(/\/lecturer\/quizzes\/\d+/)
    await expect(page.locator('article[aria-label="Question 1"]')).toBeVisible()

    // Publishing stays disabled until every question is approved.
    for (let i = 0; i < 20; i++) {
      const approve = page.getByRole('button', { name: 'Approve', exact: true }).first()
      if (!(await approve.count())) break
      await approve.click()
      await expect(approve).not.toBeVisible().catch(() => {})
    }
    await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)

    await page.getByRole('tab', { name: 'Settings' }).click()
    await page.getByLabel(/Contribution/).fill('10')
    await page.getByRole('button', { name: 'Save settings' }).click()
    await page.getByRole('tab', { name: 'Preview & publish', selected: true }).waitFor()
    await page.getByRole('button', { name: 'Publish to students' }).click()
    await dlg.getByRole('button', { name: 'Publish' }).click()
    await expect(page.getByText(/^Published /).first()).toBeVisible()
    expect(errors).toEqual([])
  })

  test('student joins, takes the quiz and sees the result and progress', async ({ page }) => {
    const errors = watchErrors(page)
    await register(page, student, 'student')

    await page.goto('/student/courses')
    await page.getByLabel('Join code').fill(shared.joinCode)
    await page.getByRole('button', { name: 'Join course' }).click()
    await expect(page.getByText(/You joined Operating Systems E2E/)).toBeVisible()

    await page.goto('/student/assigned')
    await page.getByRole('link', { name: 'Scheduling quiz E2E' }).first().click()
    await page.getByRole('button', { name: /Start|Resume/ }).first().click()
    await page.waitForURL(/attempts\/\d+$/)
    await page.locator('.st-option').first().waitFor()

    const count = await page.locator('.st-navbtn').count()
    expect(count).toBe(3)
    for (let i = 0; i < count; i++) {
      await page.locator('.st-option').first().click()
      if (i < count - 1) await page.keyboard.press('ArrowRight')
    }
    await expect(page.locator('.st-navbtn[data-answered]')).toHaveCount(count)

    // Answers survive a refresh mid-quiz.
    await page.reload()
    await expect(page.locator('.st-navbtn[data-answered]')).toHaveCount(count)

    await page.getByRole('button', { name: 'Submit quiz' }).click()
    await page.getByRole('button', { name: 'Submit now' }).click()
    await page.waitForURL(/result$/)
    await expect(page.getByText(/%/).first()).toBeVisible()

    await page.goto('/student/progress')
    await expect(page.getByText('CPU scheduling').first()).toBeVisible()
    expect(errors).toEqual([])
  })
})
