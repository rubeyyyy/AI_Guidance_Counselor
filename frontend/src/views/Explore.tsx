import { useEffect, useState } from 'react'
import { ArrowRight, CheckCircle2, Compass } from 'lucide-react'
import { api, ApiError } from '../api/client'
import type { PathwayPlan, PathwayStep, StepStatus, Student } from '../api/types'
import { ErrorNotice, Loading, PageTitle } from '../components/Shared'

function StepCard({ step, disabled, onSave }: { step: PathwayStep; disabled: boolean; onSave: (status: StepStatus, notes: string) => Promise<void> }) {
  const [status, setStatus] = useState(step.status)
  const [notes, setNotes] = useState(step.notes)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  async function save() {
    setSaving(true); setError(''); setSaved('')
    try { await onSave(status, notes); setSaved('Progress saved.') }
    catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }
  return <article className="panel pathway-step">
    <div className="pathway-step-heading"><h3>{step.status === 'completed' && <CheckCircle2 size={20} aria-label="Completed" />}{step.title}</h3><span className="pill">{step.timing}</span></div>
    <p>{step.action}</p>
    {step.weekly_minutes !== undefined && <p className="muted">Suggested weekly effort: {step.weekly_minutes} minutes within your shared time budget.</p>}
    <details><summary>How this fits your assessment</summary><p className="muted">{step.why}</p></details>
    <p className="step-evidence"><strong>Done when: </strong>{step.evidence}</p>
    <fieldset disabled={disabled || saving} className="step-tracker"><legend>Track this step</legend>
      <label htmlFor={`status-${step.id}`}>Status</label>
      <select id={`status-${step.id}`} value={status} onChange={e => { setStatus(e.target.value as StepStatus); setSaved('') }}>
        <option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="completed">Completed</option>
      </select>
      <label htmlFor={`notes-${step.id}`}>Notes, evidence, or your target date</label>
      <textarea id={`notes-${step.id}`} rows={3} maxLength={2000} value={notes} onChange={e => { setNotes(e.target.value); setSaved('') }} placeholder="What did you try? What is your next action?" />
      <button className="button secondary" onClick={() => void save()}>{saving ? 'Saving…' : 'Save progress'}</button>
    </fieldset>
    {error && <ErrorNotice error={error} />}<p role="status" className="save-notice">{saved}</p>
  </article>
}

export function Explore({ student, onChat, onEdit }: { student: Student; onChat: () => void; onEdit: () => void }) {
  const [plan, setPlan] = useState<PathwayPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [needsAssessment, setNeedsAssessment] = useState(false)
  const [needsGeneration, setNeedsGeneration] = useState(false)
  const [retry, setRetry] = useState(0)
  const [rebuilding, setRebuilding] = useState(false)
  const [confirmRebuild, setConfirmRebuild] = useState(false)
  useEffect(() => {
    let active = true
    api.pathway(student.id).then(data => { if (active) setPlan(data) }).catch(e => {
      if (active) {
        if (e instanceof ApiError && e.status === 404) setNeedsGeneration(true)
        else { setError(e.message); setNeedsAssessment(e instanceof ApiError && e.status === 409) }
      }
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [student.id, retry])
  async function generate() {
    setRebuilding(true); setError('')
    try { setPlan(await api.generatePathway(student.id)); setNeedsGeneration(false) }
    catch (e) { setError((e as Error).message) }
    finally { setRebuilding(false) }
  }
  async function rebuild() {
    setRebuilding(true); setError('')
    try { setPlan(await api.rebuildPathway(student.id)); setConfirmRebuild(false) }
    catch (e) { setError((e as Error).message) }
    finally { setRebuilding(false) }
  }
  const complete = plan?.steps.filter(s => s.status === 'completed').length ?? 0
  const percent = plan?.steps.length ? Math.round(complete / plan.steps.length * 100) : 0
  return <><PageTitle eyebrow="YOUR NEXT STEPS" title="Your pathway, one step at a time.">Turn your interests and aspirations into a plan that fits your life. Try a step, record what you learn, and adjust your direction.</PageTitle>
    {loading ? <Loading text="Loading your saved pathway…" /> : needsAssessment ? <section className="panel completion"><Compass size={40} /><h2>Start with your initial assessment.</h2><p>Your goals, strengths, and circumstances help shape a realistic plan.</p><button className="button primary" onClick={onEdit}>Complete initial assessment <ArrowRight size={16} /></button></section> : <>
      {error && <ErrorNotice error={error} retry={!plan ? () => { setLoading(true); setError(''); setNeedsAssessment(false); setRetry(r => r + 1) } : undefined} />}
      {needsGeneration && !plan && <section className="panel completion"><Compass size={40} /><h2>A pathway built for you.</h2><p>Generate short-term actions and long-term milestones with AI using your saved goals, strengths, preferences, and constraints.</p><button className="button primary" disabled={rebuilding} onClick={() => void generate()}>{rebuilding ? 'Creating your AI pathway…' : 'Generate my AI pathway'}</button>{rebuilding && <p role="status">Creating your plan can take a little time. Your progress will be saved here.</p>}</section>}
      {plan && <>
        <section className="panel pathway-overview"><p className="eyebrow">{plan.generated_by === 'ai' ? 'YOUR AI-GENERATED PLAN' : 'YOUR SAVED STARTER PLAN'}</p><h2>{plan.short_term_goal}</h2><p><strong>Long-term direction: </strong>{plan.long_term_aspiration}</p><p>{plan.pace}</p>
          <div className="assessment-progress"><div className="flex justify-between gap-3"><span>{complete} of {plan.steps.length} steps completed</span><strong>{percent}%</strong></div><progress aria-label="Pathway progress" max={100} value={percent} /></div>
          <details><summary>Resources and support to plan around</summary><ul>{plan.adaptations.map(item => <li key={item}>{item}</li>)}</ul></details>
          <p className="muted">{plan.generated_by === 'ai' ? 'AI-generated suggestions' : 'Saved starter suggestions'} based on your assessment, created {new Date(plan.generated_at).toLocaleDateString()}. Timing is flexible. Program requirements and opportunities need checking with official sources and your school counselor.</p>
        </section>
        {plan.generated_by !== 'ai' && <div className="sample-notice">This is your earlier starter plan. Rebuild it to get AI-generated steps tailored to your assessment. Your saved progress stays here until you choose to replace it.</div>}
        {plan.assessment_changed && <div role="status" className="sample-notice">Your assessment has changed. Review your saved work, then rebuild your pathway to use your latest answers. Step updates are paused until you rebuild.</div>}
        <div className="pathway-tools"><button className="button secondary" onClick={onEdit}>Update assessment</button><button className="button secondary" disabled={rebuilding} onClick={() => setConfirmRebuild(true)}>Rebuild pathway</button><button className="text-button" onClick={onChat}>Discuss my plan with AI counselor <ArrowRight size={16} /></button></div>
        {confirmRebuild && <section className="panel" aria-label="Confirm pathway rebuild"><h2>Build a fresh plan?</h2><p>AI will generate a new plan from your latest assessment. Once it is ready, it replaces your current steps, statuses, and notes. Copy any notes you want to keep first.</p><button className="button primary" disabled={rebuilding} onClick={() => void rebuild()}>{rebuilding ? 'Rebuilding…' : 'Replace plan and reset progress'}</button> <button className="button secondary" disabled={rebuilding} onClick={() => setConfirmRebuild(false)}>Keep current plan</button></section>}
        {(['short', 'long'] as const).map(horizon => <section className="pathway-section" key={horizon} aria-label={horizon === 'short' ? 'Short-term steps' : 'Long-term steps'}><h2>{horizon === 'short' ? 'Short-term: start and explore' : 'Long-term: build your direction'}</h2><p className="muted">{horizon === 'short' ? 'Use these as a sequence, at a pace that fits your weekly availability.' : 'Use what you learn to compare options and set bigger milestones.'}</p><div className="space-y-5">{plan.steps.filter(step => step.horizon === horizon).map(step => <StepCard key={`${plan.generated_at}-${step.id}`} step={step} disabled={plan.assessment_changed || rebuilding} onSave={async (status, notes) => { const updated = await api.updatePathwayStep(student.id, step.id, status, notes); setPlan(updated) }} />)}</div></section>)}
      </>}
    </>}
  </>
}
