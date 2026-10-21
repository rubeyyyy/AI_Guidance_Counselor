import { useState } from 'react'
import { ArrowRight, BookOpen, Compass, GraduationCap, LayoutGrid, Leaf, MessageCircle, ShieldCheck, UserRound } from 'lucide-react'
import type { Student } from './api/types'
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
  const [student, setStudent] = useState<Student | null>(null)
  const [view, setView] = useState<View>('home')
  const [conversation, setConversation] = useState<number | null>(null)
  function navigate(next: View) { setView(next); if (next === 'chat') setConversation(null) }
  function openConversation(id: number) { setConversation(id); setView('chat') }
  return <div className="app-shell">
    <a href="#main" className="skip-link">Skip to content</a>
    <aside className="sidebar">
      <a href="#main" className="brand" onClick={() => navigate('home')}><span className="brand-mark"><Leaf size={24} /></span><span>PathBridge <b>AI</b><small>A little clarity. A world of possibility.</small></span></a>
      <div className="sidebar-label">YOUR JOURNEY</div>
      <nav aria-label="Main navigation">{navigation.map(({ id, label, icon: Icon }) => <button key={id} aria-current={view === id ? 'page' : undefined} disabled={id !== 'home' && !student} onClick={() => navigate(id)}><Icon size={19} aria-hidden="true" />{label}{view === id && <span className="nav-dot" />}</button>)}</nav>
      <div className="sidebar-note"><GraduationCap size={24} /><strong>You don’t need it all figured out.</strong><p>Small steps count. We’re here to help you find yours.</p></div>
      <div className="sidebar-bottom"><ShieldCheck size={17} /><span>Built for your possibilities</span></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span className="topbar-tag">STUDENT SPACE</span><div className="student-chip"><span className="avatar"><UserRound size={17} /></span>{student ? <span>{student.display_name || 'Student'} <small>Development ID {student.id}</small></span> : <span>Your journey starts here</span>}</div></header>
      <main id="main" tabIndex={-1} key={student?.id ?? 'guest'}>
        <div className="development-banner"><ShieldCheck size={16} aria-hidden="true" /><span><strong>Development preview.</strong> Use synthetic data only. Student selection has no authentication and is not suitable for real records.</span></div>
        {view === 'home' && <Welcome student={student} onStudent={setStudent} onStart={() => navigate('assessment')} onChat={() => navigate('chat')} />}
        {student && view === 'assessment' && <Assessment student={student} onDone={() => navigate('profile')} />}
        {student && view === 'profile' && <ProfileView student={student} onEdit={() => navigate('assessment')} onChat={() => navigate('chat')} />}
        {student && view === 'chat' && <Chat student={student} initialConversation={conversation} />}
        {student && view === 'explore' && <Explore student={student} onChat={() => navigate('chat')} onOpen={openConversation} />}
        <footer className="page-footer"><span><Leaf size={14} /> PathBridge AI</span><p>Explore at your own pace. Your future is yours to shape.</p><a href="#main">Back to top <ArrowRight size={13} /></a></footer>
      </main>
    </div>
  </div>
}
