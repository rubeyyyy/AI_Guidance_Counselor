import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, BookOpen, GraduationCap, LayoutGrid, Leaf, LockKeyhole, Mail, ShieldCheck, UserRound } from 'lucide-react'
import { api } from '../api/client'
import type { AuthUser } from '../api/client'
import { Welcome } from './Welcome'

type Mode = 'login' | 'register' | 'verify' | 'forgot' | 'reset'
const titles: Record<Mode, string> = {
  register: 'A new chapter starts with you.', login: 'Welcome back.',
  verify: 'Check your inbox.', forgot: 'Let’s get you back on your path.', reset: 'A fresh start for your password.',
}

export function AuthPage({ onAuthenticated, message }: { onAuthenticated: (user: AuthUser) => Promise<void>; message: string }) {
  const [mode, setMode] = useState<Mode>('register')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [challenge, setChallenge] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [cooldown, setCooldown] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const previousMode = useRef(mode)
  useEffect(() => {
    if (previousMode.current !== mode) {
      previousMode.current = mode
      heading.current?.focus()
    }
  }, [mode])
  useEffect(() => {
    if (!cooldown) return
    const timer = window.setTimeout(() => setCooldown(seconds => Math.max(0, seconds - 1)), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])
  function open(next: Mode) {
    setMode(next); setPassword(''); setConfirm(''); setCode(''); setError(''); setNotice(''); setChallenge('')
  }
  function focusAccess() { document.getElementById('student-access')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); heading.current?.focus({ preventScroll: true }) }
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      if (mode === 'register') {
        const result = await api.startRegistration(email, password, name)
        setChallenge(result.challenge_id); setNotice(result.message); setPassword(''); setMode('verify'); setCooldown(60)
      } else if (mode === 'login') {
        const user = await api.authenticate('login', email, password)
        setPassword(''); await onAuthenticated(user)
      } else if (mode === 'verify') {
        await onAuthenticated(await api.verifyEmail(challenge, code))
      } else if (mode === 'forgot') {
        const result = await api.forgotPassword(email)
        setChallenge(result.challenge_id); setNotice(result.message); setCode(''); setMode('reset'); setCooldown(60)
      } else {
        if (password !== confirm) throw new Error('Your passwords don’t match. Please check both fields.')
        const result = await api.resetPassword(challenge, code, password)
        open('login'); setNotice(result.message)
      }
    } catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }
  async function resend() {
    setBusy(true); setError('')
    try {
      const result = mode === 'verify' ? await api.resendVerification(email, challenge) : await api.resendReset(email, challenge)
      setNotice(result.message); setCode(''); setCooldown(60)
    } catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }
  const isCode = mode === 'verify' || mode === 'reset'
  const needsPassword = mode === 'register' || mode === 'login' || mode === 'reset'
  return <div className="app-shell auth-shell">
    <a href="#main" className="skip-link">Skip to content</a>
    <aside className="sidebar">
      <a href="#main" className="brand"><span className="brand-mark"><Leaf size={24} /></span><span>PathBridge <b>AI</b><small>A little clarity. A world of possibility.</small></span></a>
      <div className="sidebar-label">YOUR JOURNEY</div>
      <nav aria-label="Welcome navigation">
        <a href="#main" aria-current="page"><LayoutGrid size={19} />Your starting point<span className="nav-dot" /></a>
        <a href="#student-access"><UserRound size={19} />Your student space</a>
        <a href="#how-it-works"><BookOpen size={19} />How it works</a>
      </nav>
      <div className="sidebar-note"><GraduationCap size={24} /><strong>You don’t need it all figured out.</strong><p>Small steps count. We’re here to help you find yours.</p></div>
      <div className="sidebar-bottom"><ShieldCheck size={17} /><span>Built for your possibilities</span></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span className="topbar-tag">YOUR NEXT CHAPTER</span><button className="button secondary" onClick={() => { open('login'); focusAccess() }} disabled={busy}>Already a member? Sign in <ArrowRight size={15} /></button></header>
      <main id="main" tabIndex={-1}>
        <Welcome student={null} onStart={focusAccess}>
          <section className="student-selector auth-access" id="student-access" aria-labelledby="account-heading">
            <div className="auth-intro">
              <span className="auth-emblem">{isCode ? <Mail size={25} /> : <Leaf size={25} />}</span>
              <p className="eyebrow">YOUR STUDENT SPACE</p>
              <h2 ref={heading} tabIndex={-1} id="account-heading">{titles[mode]}</h2>
              <p>{mode === 'register' ? 'Create an account to save your assessment, discover new possibilities, and pick up right where you left off.' : mode === 'login' ? 'Your goals, your progress, your possibilities. Sign in to continue your journey.' : isCode ? `Enter the 8-digit code from the email for ${email}. Codes expire after 10 minutes.` : 'Enter the email you use for PathBridge. If an active account exists, we’ll send a code to reset your password.'}</p>
              <div className="auth-trust"><LockKeyhole size={17} /><span>{isCode ? 'Never share your code with anyone.' : 'Your saved progress belongs to your account.'}</span></div>
            </div>
            <div className="auth-form-panel">
              {(mode === 'register' || mode === 'login') && <div className="auth-switch" role="group" aria-label="Account access"><button type="button" aria-pressed={mode === 'register'} disabled={busy} onClick={() => open('register')}>New student</button><button type="button" aria-pressed={mode === 'login'} disabled={busy} onClick={() => open('login')}>Returning student</button></div>}
              <form onSubmit={submit} aria-label="Account form" className="auth-form">
                {mode === 'register' && <label>Display name <span>(optional)</span><input value={name} onChange={e => setName(e.target.value)} maxLength={100} autoComplete="nickname" placeholder="What would you like us to call you?" disabled={busy} /></label>}
                {!isCode && <label>Email<input type="email" required maxLength={254} autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" disabled={busy} /></label>}
                {isCode && <label>Email code<input className="auth-code" type="text" inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{8}" minLength={8} maxLength={8} value={code} onChange={e => setCode(e.target.value.replace(/\s/g, ''))} placeholder="8-digit code" disabled={busy} aria-describedby="code-help" /></label>}
                {isCode && <p id="code-help" className="auth-help">Check your spam folder, too. If you closed this page, start a new request. {mode === 'reset' && 'Use the code from this password-reset request.'}</p>}
                {needsPassword && <label>{mode === 'reset' ? 'New password' : 'Password'}<input type="password" required minLength={mode === 'login' ? 1 : 12} maxLength={128} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} placeholder={mode === 'login' ? 'Your password' : 'Choose a long, unique passphrase'} disabled={busy} aria-describedby={mode === 'login' ? undefined : 'password-help'} /></label>}
                {mode === 'reset' && <label>Confirm new password<input type="password" required minLength={12} maxLength={128} autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} disabled={busy} /></label>}
                {needsPassword && mode !== 'login' && <p id="password-help" className="auth-help">Use 12–128 characters. A long, unique passphrase works well.</p>}
                {mode === 'login' && <button type="button" className="text-button auth-forgot" disabled={busy} onClick={() => open('forgot')}>Forgot password?</button>}
                {(error || message) && <p className="error" role="alert">{error || message}</p>}
                {notice && <p className="auth-notice" role="status">{notice}</p>}
                <button className="button primary auth-submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'register' ? 'Create account' : mode === 'login' ? 'Sign in' : mode === 'verify' ? 'Verify email & continue' : mode === 'forgot' ? 'Send reset code' : 'Update password'}<ArrowRight size={17} /></button>
              </form>
              {isCode && <button className="text-button auth-secondary" type="button" disabled={busy || cooldown > 0} onClick={() => void resend()}>{cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}</button>}
              <div className="auth-alternative">{mode === 'register' ? <>Already have an account? <button className="text-button" disabled={busy} onClick={() => open('login')}>Sign in instead</button></> : mode === 'login' ? <>New here? <button className="text-button" disabled={busy} onClick={() => open('register')}>Create a student account</button></> : <button className="text-button" disabled={busy} onClick={() => open(mode === 'verify' ? 'register' : 'login')}>{mode === 'verify' ? 'Change email or start again' : 'Back to sign in'}</button>}</div>
            </div>
          </section>
        </Welcome>
        <footer className="page-footer"><span><Leaf size={14} /> PathBridge AI</span><p>Explore at your own pace. Your future is yours to shape.</p><a href="#main">Back to top <ArrowRight size={13} /></a></footer>
      </main>
    </div>
  </div>
}
