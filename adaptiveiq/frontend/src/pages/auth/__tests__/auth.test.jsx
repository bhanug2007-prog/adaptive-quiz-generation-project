import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api/endpoints', () => ({
  authApi: {
    me: vi.fn(), login: vi.fn(), register: vi.fn(), logout: vi.fn(), config: vi.fn(),
    verifyEmail: vi.fn(), resendVerification: vi.fn(),
  },
}))

const { authApi } = await import('../../../api/endpoints')
const { AuthProvider } = await import('../../../auth/AuthProvider')
const { default: SignIn, safeNext } = await import('../SignIn')
const { default: Register, passwordProblem } = await import('../Register')
const { default: VerifyEmail } = await import('../VerifyEmail')
const { default: RequireRole } = await import('../../../auth/RequireRole')

const STUDENT = { id: 2, email: 'student@example.edu', full_name: 'Sample Student', role: 'student', email_verified: true }

function app(path, extra = null) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/register" element={<Register />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/student" element={<RequireRole role="student" />}>
            <Route index element={<p>student home</p>} />
            <Route path="progress" element={<p>student progress</p>} />
          </Route>
          <Route path="/lecturer" element={<RequireRole role="lecturer" />}>
            <Route index element={<p>lecturer home</p>} />
          </Route>
          {extra}
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  authApi.me.mockRejectedValue(Object.assign(new Error('Please sign in.'), { status: 401 }))
  authApi.config.mockResolvedValue({ lecturer_signup_enabled: true, allowed_email_domains: [], email_verification_required: true })
})

describe('password rules match the backend', () => {
  it.each([
    ['short1', 'Use at least 8 characters.'],
    ['onlyletters', 'Include at least one letter and one number.'],
    ['12345678', 'Include at least one letter and one number.'],
    ['Passw0rd1', null],
    ['é'.repeat(37) + '1', 'Use at most 72 bytes.'],
  ])('%s', (p, msg) => expect(passwordProblem(p)).toBe(msg))
})

describe('redirect after sign-in', () => {
  it('only follows same-app paths for the right role', () => {
    expect(safeNext('/student/progress', STUDENT)).toBe('/student/progress')
    expect(safeNext('//evil.example', STUDENT)).toBe('/student')
    expect(safeNext('https://evil.example', STUDENT)).toBe('/student')
    expect(safeNext('/lecturer', STUDENT)).toBe('/student')
    expect(safeNext(null, STUDENT)).toBe('/student')
  })
})

describe('sign in', () => {
  it('validates before calling the API', async () => {
    app('/signin')
    await userEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter your email.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(authApi.login).not.toHaveBeenCalled()
  })

  it('shows the backend error message', async () => {
    authApi.login.mockRejectedValue(new Error('Email or password is not correct.'))
    app('/signin')
    await userEvent.type(await screen.findByLabelText('Email'), 'student@example.edu')
    await userEvent.type(screen.getByLabelText('Password'), 'wrongpass1')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Email or password is not correct.')).toBeInTheDocument()
  })

  it('goes to the page the user asked for', async () => {
    authApi.login.mockResolvedValue(STUDENT)
    app('/signin?next=%2Fstudent%2Fprogress')
    await userEvent.type(await screen.findByLabelText('Email'), 'student@example.edu')
    await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd1')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('student progress')).toBeInTheDocument()
    expect(authApi.login).toHaveBeenCalledWith('student@example.edu', 'Passw0rd1')
  })
})

describe('register', () => {
  it('asks lecturers for the invite code and sends it', async () => {
    authApi.register.mockResolvedValue({ ...STUDENT, role: 'lecturer', email_verified: false })
    app('/register')
    await userEvent.click(await screen.findByLabelText('Lecturer'))
    await userEvent.type(screen.getByLabelText('Full name'), 'Dr Test')
    await userEvent.type(screen.getByLabelText('Email'), 'lec@example.edu')
    await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd1')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'Passw0rd1')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Enter the invite code.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Lecturer invite code'), 'code-123')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(authApi.register).toHaveBeenCalled())
    expect(authApi.register.mock.calls[0][0]).toMatchObject({ role: 'lecturer', invite_code: 'code-123', email: 'lec@example.edu' })
    expect(await screen.findByText('lecturer home')).toBeInTheDocument()
  })

  it('enforces allowed email domains and matching passwords', async () => {
    authApi.config.mockResolvedValue({ lecturer_signup_enabled: false, allowed_email_domains: ['iiitdwd.ac.in'], email_verification_required: true })
    app('/register')
    await userEvent.type(await screen.findByLabelText('Full name'), 'A Student')
    await userEvent.type(screen.getByLabelText('Email'), 'a@gmail.com')
    await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd1')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'Passw0rd2')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Use an email ending in @iiitdwd.ac.in.')).toBeInTheDocument()
    expect(screen.getByText('The passwords do not match.')).toBeInTheDocument()
    expect(authApi.register).not.toHaveBeenCalled()
  })

  it('explains when lecturer sign-up is off', async () => {
    authApi.config.mockResolvedValue({ lecturer_signup_enabled: false, allowed_email_domains: [], email_verification_required: true })
    app('/register')
    await userEvent.click(await screen.findByLabelText('Lecturer'))
    expect(await screen.findByText(/Lecturer sign-up is turned off/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled()
  })
})

describe('route guard and verification', () => {
  it('sends signed-out users to sign in and keeps the target', async () => {
    app('/student/progress')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('sends a student away from lecturer pages', async () => {
    authApi.me.mockResolvedValue(STUDENT)
    app('/lecturer')
    expect(await screen.findByText('student home')).toBeInTheDocument()
  })

  it('verifies the email from the link', async () => {
    authApi.verifyEmail.mockResolvedValue({ ...STUDENT, email_verified: true })
    app('/verify-email?token=abcdefghijklmnop')
    expect(await screen.findByText('Email verified')).toBeInTheDocument()
    expect(authApi.verifyEmail).toHaveBeenCalledTimes(1)
  })

  it('shows why a bad link failed', async () => {
    authApi.verifyEmail.mockRejectedValue(new Error('This verification link is not valid or has expired.'))
    app('/verify-email?token=abcdefghijklmnop')
    expect(await screen.findByText(/not valid or has expired/)).toBeInTheDocument()
  })
})
