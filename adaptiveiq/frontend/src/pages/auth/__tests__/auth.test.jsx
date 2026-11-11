import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api/endpoints', () => ({
  authApi: {
    me: vi.fn(), login: vi.fn(), register: vi.fn(), logout: vi.fn(), config: vi.fn(),
    verifyEmail: vi.fn(), resendVerification: vi.fn(),
    forgotPassword: vi.fn(), verifyResetToken: vi.fn(), resetPassword: vi.fn(),
  },
}))

const { authApi } = await import('../../../api/endpoints')
const { AuthProvider } = await import('../../../auth/AuthProvider')
const { default: SignIn, safeNext } = await import('../SignIn')
const { default: Register, passwordProblem } = await import('../Register')
const { default: VerifyEmail } = await import('../VerifyEmail')
const { default: ForgotPassword } = await import('../ForgotPassword')
const { default: ResetPassword } = await import('../ResetPassword')
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
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
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

describe('password recovery', () => {
  it('links cleanly from Sign in to Forgot password', async () => {
    app('/signin')
    const link = await screen.findByRole('link', { name: 'Forgot password?' })
    await userEvent.click(link)
    expect(await screen.findByRole('heading', { name: 'Forgot your password?' })).toBeInTheDocument()
  })

  it('validates email, sends request, and displays neutral confirmation without leaking existence', async () => {
    authApi.forgotPassword.mockResolvedValue({
      message: 'If an account with that email exists, we sent a password reset link.',
    })
    app('/forgot-password')
    await userEvent.click(await screen.findByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText('Enter your email.')).toBeInTheDocument()
    expect(authApi.forgotPassword).not.toHaveBeenCalled()

    await userEvent.type(screen.getByLabelText('Email'), 'nobody@example.edu')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText('Check your email')).toBeInTheDocument()
    expect(screen.getByText(/If an account with that email exists/)).toBeInTheDocument()
    expect(authApi.forgotPassword).toHaveBeenCalledWith('nobody@example.edu')
  })

  it('shows error alert when forgot-password is rate limited', async () => {
    authApi.forgotPassword.mockRejectedValue(new Error('Too many password reset requests. Try again in 15 minute(s).'))
    app('/forgot-password')
    await userEvent.type(await screen.findByLabelText('Email'), 'student@example.edu')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many password reset requests')
  })

  it('rejects missing tokens on reset-password without calling verify', async () => {
    app('/reset-password')
    expect(await screen.findByText('Reset link not valid')).toBeInTheDocument()
    expect(authApi.verifyResetToken).not.toHaveBeenCalled()
  })

  it('shows loading then expired state for expired reset links', async () => {
    let rejectVerify
    authApi.verifyResetToken.mockImplementation(() => new Promise((_, rej) => { rejectVerify = rej }))
    app('/reset-password?token=expiredTokenValue12345678901234567890')
    expect(await screen.findByText(/Checking your reset link/)).toBeInTheDocument()
    rejectVerify(new Error('This password reset link has expired. Request a new one.'))
    expect(await screen.findByText('Reset link expired')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Request a new reset link' })).toHaveAttribute('href', '/forgot-password')
  })

  it('shows invalid-token state for reused or unknown reset links', async () => {
    authApi.verifyResetToken.mockRejectedValue(
      new Error('This password reset link is invalid or has already been used.'),
    )
    app('/reset-password?token=reusedTokenValue12345678901234567890')
    expect(await screen.findByText('Reset link not valid')).toBeInTheDocument()
    expect(screen.getByText(/invalid or has already been used/)).toBeInTheDocument()
  })

  it('validates password policy, resets password, never persists token to storage, and transitions to success', async () => {
    const token = 'validTokenValue1234567890123456789012'
    authApi.verifyResetToken.mockResolvedValue({ valid: true })
    authApi.resetPassword.mockResolvedValue(null)

    app(`/reset-password?token=${token}`)
    const pwInput = await screen.findByLabelText('New password')
    await userEvent.type(pwInput, 'short')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'mismatch')
    await userEvent.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(await screen.findByText('Use at least 8 characters.')).toBeInTheDocument()
    expect(screen.getByText('The passwords do not match.')).toBeInTheDocument()
    expect(authApi.resetPassword).not.toHaveBeenCalled()

    await userEvent.clear(pwInput)
    await userEvent.clear(screen.getByLabelText('Confirm new password'))
    await userEvent.type(pwInput, 'N3wRecoveredPass')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'N3wRecoveredPass')
    await userEvent.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(await screen.findByText('Password reset complete')).toBeInTheDocument()
    expect(authApi.resetPassword).toHaveBeenCalledWith(token, 'N3wRecoveredPass')
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })
})
