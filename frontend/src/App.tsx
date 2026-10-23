import { api, ApiError, clearCsrf } from './api/client'
import type { AuthUser } from './api/client'
import { AuthPage } from './views/Auth'
import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, BookOpen, Compass, GraduationCap, LayoutGrid, Leaf, MessageCircle, ShieldCheck, UserRound } from 'lucide-react'
import type { Progress, Student } from './api/types'
import { Welcome } from './views/Welcome'
import { Assessment } from './views/Assessment'
import { ProfileView } from './views/Profile'
import { Chat } from './views/Chat'
import { Explore } from './views/Explore'

type View = 'home' | 'assessment' | 'profile' | 'chat' | 'explore'
const navigation = [
  { id: 'home', label: 'Your starting point', icon: LayoutGrid },
  { id: 'assessment', label: 'Initial assessment', icon: BookOpen },
  { id: 'profile', label: 'My profile', icon: UserRound },
  { id: 'chat', label: 'AI counselor', icon: MessageCircle },
  { id: 'explore', label: 'Explore pathways', icon: Compass },
] as const

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [authError, setAuthError] = useState('')
  const [student, setStudent] = useState<Student | null>(null)
  const [assessmentComplete, setAssessmentComplete] = useState(false)
  const [view, setView] = useState<View>('home')
  const [conversation, setConversation] = useState<number | null>(null)
  const updateProgress = useCallback((progress: Progress) => {
    setAssessmentComplete(progress.is_complete)
    if (!progress.is_complete) setView(current => current === 'profile' || current === 'chat' ? 'assessment' : current)
  }, [])
  useEffect(() => {
    let active = true
    async function restore() {
      try {
        const current = await api.me()
        const profile = current.role === 'student' && current.student_id ? await api.student(current.student_id) : null
        const progress = profile ? await api.progress(profile.id) : null
        if (active) { setUser(current); setStudent(profile); setAssessmentComplete(progress?.is_complete === true) }
      } catch (error) { if (active && (!(error instanceof ApiError) || error.status !== 401)) setAuthError((error as Error).message) }
      finally { if (active) setLoading(false) }
    }
    function expired() { clearCsrf(); setUser(null); setStudent(null); setAssessmentComplete(false); setView('home'); setConversation(null); setAuthError('Your session ended. Please sign in again.') }
    window.addEventListener('pathbridge:session-expired', expired)
    void restore()
    return () => { active = false; window.removeEventListener('pathbridge:session-expired', expired) }
  }, [])
  async function authenticated(current: AuthUser) {
    const profile = current.role === 'student' && current.student_id ? await api.student(current.student_id) : null
    const progress = profile ? await api.progress(profile.id) : null
    setAssessmentComplete(progress?.is_complete === true)
    setStudent(profile); setUser(current); setAuthError(''); setView('home'); setConversation(null)
  }
  async function logout() {
    try { await api.logout(); setUser(null); setStudent(null); setAssessmentComplete(false); setView('home'); setConversation(null); setAuthError('') }
    catch (error) { setAuthError((error as Error).message) }
  }
  if (loading) return <main className="p-8" role="status">Restoring your session…</main>
  if (!user) return <AuthPage onAuthenticated={authenticated} message={authError} />
  if (user.role === 'counselor' || !student) return <main className="p-8"><h1>{user.role === 'counselor' ? 'Counselor account' : 'Student profile unavailable'}</h1><p>{user.role === 'counselor' ? 'The counselor workspace is not available yet. Student records require an assignment.' : 'Please contact your school support team.'}</p>{authError && <p role="alert">{authError}</p>}<button className="button secondary" onClick={() => void logout()}>Sign out</button></main>
  function navigate(next: View) { setView((next === 'profile' || next === 'chat') && !assessmentComplete ? 'assessment' : next); if (next === 'chat') setConversation(null) }
  return <div className="app-shell">
    <a href="#main" className="skip-link">Skip to content</a>
    <aside className="sidebar">
      <a href="#main" className="brand" onClick={() => navigate('home')}><span className="brand-mark"><Leaf size={24} /></span><span>PathBridge <b>AI</b><small>A little clarity. A world of possibility.</small></span></a>
      <div className="sidebar-label">YOUR JOURNEY</div>
      <nav aria-label="Main navigation">{navigation.map(({ id, label, icon: Icon }) => <button key={id} aria-current={view === id ? 'page' : undefined} disabled={(id === 'profile' || id === 'chat') && !assessmentComplete} title={(id === 'profile' || id === 'chat') && !assessmentComplete ? 'Complete the initial assessment to unlock this page.' : undefined} onClick={() => navigate(id)}><Icon size={19} aria-hidden="true" />{label}{view === id && <span className="nav-dot" />}</button>)}</nav>
      {!assessmentComplete && <p className="assessment-lock-note">Complete the required initial assessment questions to unlock My profile and AI counselor.</p>}
      <div className="sidebar-note"><GraduationCap size={24} /><strong>You don’t need it all figured out.</strong><p>Small steps count. We’re here to help you find yours.</p></div>
      <div className="sidebar-bottom"><ShieldCheck size={17} /><span>Built for your possibilities</span></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><button className="button secondary" onClick={() => void logout()}>Sign out</button>{authError && <p role="alert">{authError}</p>}<span className="topbar-tag">STUDENT SPACE</span><div className="student-chip"><span className="avatar"><UserRound size={17} /></span>{student ? <span>{student.display_name || 'Student'} <small>Student ID {student.id}</small></span> : <span>Your journey starts here</span>}</div></header>
      <main id="main" tabIndex={-1} key={student?.id ?? 'guest'}>
        {view === 'home' && <Welcome student={student} onStart={() => navigate('assessment')} />}
        {student && view === 'assessment' && <Assessment student={student} onProgress={updateProgress} onDone={() => navigate('profile')} />}
        {student && assessmentComplete && view === 'profile' && <ProfileView student={student} onEdit={() => navigate('assessment')} onChat={() => navigate('chat')} />}
        {student && assessmentComplete && view === 'chat' && <Chat student={student} initialConversation={conversation} />}
        {student && view === 'explore' && <Explore student={student} onChat={() => navigate('chat')} onEdit={() => navigate('assessment')} />}
        <footer className="page-footer"><span><Leaf size={14} /> PathBridge AI</span><p>Explore at your own pace. Your future is yours to shape.</p><a href="#main">Back to top <ArrowRight size={13} /></a></footer>
      </main>
    </div>
  </div>
}
