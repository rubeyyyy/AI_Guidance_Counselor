import { useEffect, useState } from 'react'
import { ArrowRight, PencilLine } from 'lucide-react'
import { api } from '../api/client'
import type { AnswerValue, Profile, Student } from '../api/types'
import { ErrorNotice, Loading, PageTitle } from '../components/Shared'

const groups: [string, string[]][] = [
  ['Academic background', ['academic_background', 'grade', 'current_program', 'gpa']],
  ['Interests', ['interests', 'career_interest_reason']],
  ['Career aspirations', ['career_aspirations', 'long_term_aspirations']],
  ['Skills', ['skills', 'technical_skills', 'soft_skills', 'technical_skills_raw', 'related_experiences', 'certifications']],
  ['Learning preferences', ['learning_preferences']],
  ['Available resources', ['resources', 'has_personal_laptop', 'has_reliable_internet', 'weekly_learning_hours']],
  ['Constraints', ['constraints', 'biggest_obstacle', 'accessibility_needs', 'socioeconomic_factors', 'other_obstacle']],
  ['Goals', ['short_term_goal', 'goals']],
]
const format = (value: AnswerValue) => value == null ? 'Not answered yet' : Array.isArray(value) ? value.join(', ') || 'Not answered yet' : String(value)
const label = (key: string) => key.replaceAll('_', ' ')

export function ProfileView({ student, onEdit, onChat }: { student: Student; onEdit: () => void; onChat: () => void }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    api.profile(student.id).then(p => { if (active) { setProfile(p); setError('') } }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [student.id, retry])
  if (error) return <ErrorNotice error={error} retry={() => { setError(''); setRetry(r => r + 1) }} />
  if (!profile) return <Loading text="Loading your saved profile…" />
  const known = new Set(groups.flatMap(([, keys]) => keys))
  const additional = profile.fields.filter(f => !known.has(f.key))
  return <><PageTitle eyebrow="YOUR STARTING POINT" title="A picture of you.">Your saved answers help shape the conversation. There’s room to grow and change.</PageTitle>
    <div className="profile-summary"><div><strong>{profile.progress.answered_questions} of {profile.progress.total_questions} answers saved</strong><p>{profile.progress.is_complete ? 'Required questions complete' : 'Your assessment is still in progress'}</p></div><button className="button secondary" onClick={onEdit}><PencilLine size={16} />Edit assessment</button></div>
    {profile.is_sample && <div className="sample-notice">This profile uses a sample questionnaire. Sample answers are shown separately and are not interpreted as academic or career information.</div>}
    <div className="grid gap-5 md:grid-cols-2">{groups.map(([title, keys]) => {
      const fields = profile.fields.filter(f => keys.includes(f.key))
      return <section className="panel profile-card" key={title}><h2>{title}</h2>{fields.length ? <dl>{fields.map(f => <div key={f.key}><dt>{label(f.key)}</dt><dd className={f.value == null ? 'muted' : ''}>{format(f.value)}</dd></div>)}</dl> : <p className="muted">Not provided by the current questionnaire.</p>}</section>
    })}</div>
    {additional.length > 0 && <section className="panel mt-5"><h2>{profile.is_sample ? 'Sample questionnaire answers' : 'Other saved answers'}</h2><dl className="profile-fields">{additional.map(f => <div key={f.key}><dt>{label(f.key)}</dt><dd>{format(f.value)}</dd></div>)}</dl></section>}
    <div className="next-step"><div><h2>Let’s connect the dots.</h2><p>Talk through your questions with the AI guidance counselor.</p></div><button className="button primary" onClick={onChat}>Open counselor <ArrowRight size={17} /></button></div>
  </>
}
