import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, BookOpen, Compass, MessageCircle, Sprout, Check } from 'lucide-react'
import { api } from '../api/client'
import type { Student } from '../api/types'
import { ErrorNotice } from '../components/Shared'

export function Welcome({ student, onStudent, onStart, onChat }: { student: Student | null; onStudent: (s: Student) => void; onStart: () => void; onChat: () => void }) {
  const [name, setName] = useState('')
  const [id, setId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function select(event: FormEvent, create: boolean) {
    event.preventDefault(); setError(''); setBusy(true)
    try { onStudent(create ? await api.createStudent(name) : await api.student(Number(id))) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <>
    <section className="welcome-hero">
      <div><p className="eyebrow"><span className="tiny-dot" /> A NEXT STEP THAT FEELS LIKE YOU</p><h1>Your future.<br />Your possibilities.<br /><em>Your path.</em></h1><p className="hero-description">You bring the curiosity. We’ll help you explore education and career pathways that connect with who you are—and where you want to go.</p><button className="button primary" disabled={!student} onClick={onStart}>{student ? 'Start or resume my assessment' : 'Choose a development student below'}<ArrowRight size={18} /></button><p className="hero-footnote"><Check size={15} /> At your pace <span>·</span> Optional questions can be skipped</p></div>
      <div className="path-art" aria-hidden="true"><div className="art-sun" /><svg viewBox="0 0 400 360"><path d="M-30 310 Q90 100 180 230 T440 105" fill="none" stroke="#d4dfcb" strokeWidth="100" /><path d="M-30 310 Q90 100 180 230 T440 105" fill="none" stroke="#f8f6ee" strokeWidth="46" /><path d="M-30 310 Q90 100 180 230 T440 105" fill="none" stroke="#c3cbb8" strokeWidth="2" strokeDasharray="8 9" /></svg><div className="art-card art-card-top"><span className="art-icon"><Compass size={22} /></span><div><strong>More than one way forward</strong><small>Find what sparks your curiosity.</small></div></div><div className="art-card art-card-bottom"><span className="art-icon gold"><Sprout size={22} /></span><div><strong>Start small. Grow from here.</strong><small>Every next step matters.</small></div></div><div className="art-caption">YOUR PATH DOESN’T HAVE TO BE A STRAIGHT LINE.</div></div>
    </section>
    <section className="journey-section"><div className="section-heading"><h2>A little reflection. A clearer direction.</h2><span>HERE’S HOW IT WORKS</span></div><div className="grid gap-5 md:grid-cols-3">{[
      { icon: BookOpen, number: '01', title: 'Start with you', text: 'A short initial assessment helps us understand your starting point. Skip optional questions and update answers later.' },
      { icon: MessageCircle, number: '02', title: 'Talk it through', text: 'Ask questions, share your interests, and explore practical next steps with your AI guidance counselor.' },
      { icon: Compass, number: '03', title: 'Explore what’s possible', text: 'Revisit ideas from your conversations. Bring your questions to a trusted human counselor.' },
    ].map(({ icon: Icon, number, title, text }) => <article className="step-card" key={number}><div className="flex items-center justify-between"><span className="step-icon"><Icon size={22} /></span><span className="step-number">{number}</span></div><h3>{title}</h3><p>{text}</p></article>)}</div></section>
    {import.meta.env.DEV ? <section className="student-selector" aria-labelledby="student-access"><div><p className="eyebrow">DEVELOPMENT ONLY · NO LOGIN</p><h2 id="student-access">Open a practice student space</h2><p>Use a fictional label or a known development student ID. Your ID is shown above after selection; browser refresh clears the selection.</p>{student && <p className="success" role="status">Selected student #{student.id}. <button className="text-button" onClick={onStart}>Continue assessment</button> or <button className="text-button" onClick={onChat}>open counselor</button>.</p>}</div><div className="selector-forms"><form onSubmit={e => select(e, true)}><label htmlFor="student-name">Fictional display name <span>(optional)</span></label><div className="input-action"><input id="student-name" value={name} maxLength={100} onChange={e => setName(e.target.value)} placeholder="e.g. Practice student" disabled={busy} /><button className="button primary" disabled={busy}>{busy ? 'Please wait…' : 'Create student'}</button></div></form><form onSubmit={e => select(e, false)}><label htmlFor="student-id">Or use an existing development student ID</label><div className="input-action"><input id="student-id" type="number" min="1" max={Number.MAX_SAFE_INTEGER} step="1" required value={id} onChange={e => setId(e.target.value)} placeholder="Student ID" disabled={busy} /><button className="button secondary" disabled={busy}>Load student</button></div></form>{error && <ErrorNotice error={error} />}</div></section> : <section className="panel"><h2>Student access is available in development only.</h2><p>Production student access requires authentication and authorization, which are not implemented in this preview.</p></section>}
    <aside className="counselor-note"><span className="note-icon"><MessageCircle size={22} /></span><div><strong>A helpful companion, with a human in your corner.</strong><p>AI guidance supports exploration. It does not replace a qualified human counselor. Verify important education, financial aid, and career decisions with one.</p></div></aside>
  </>
}
