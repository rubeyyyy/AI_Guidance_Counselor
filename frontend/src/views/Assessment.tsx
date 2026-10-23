import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, ArrowRight, CheckCircle2 } from 'lucide-react'
import { api } from '../api/client'
import type { AnswerValue, Progress, Question, Student } from '../api/types'
import { ErrorNotice, Loading, PageTitle } from '../components/Shared'

export function Assessment({ student, onDone, onProgress }: { student: Student; onDone: () => void; onProgress?: (progress: Progress) => void }) {
  const [allQuestions, setQuestions] = useState<Question[]>([])
  const [answers, setAnswers] = useState<Record<number, AnswerValue>>({})
  const [progress, setProgress] = useState<Progress | null>(null)
  const [index, setIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [finished, setFinished] = useState(false)
  const [retry, setRetry] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    let active = true
    Promise.all([api.questions(), api.answers(student.id), api.progress(student.id)]).then(([qs, saved, p]) => {
      if (!active) return
      const values = Object.fromEntries(saved.map(a => [a.question_id, a.value]))
      setQuestions(qs); setAnswers(values); setProgress(p)
      const visible = qs.filter(q => !q.required_when || Object.entries(q.required_when).every(([key, expected]) => values[qs.find(parent => parent.key === key)?.id ?? -1] === expected))
      const first = visible.findIndex(q => values[q.id] == null)
      setIndex(first < 0 ? 0 : first); setError(''); setLoading(false)
    }).catch(e => { if (active) { setError(e.message); setLoading(false) } })
    return () => { active = false }
  }, [student.id, retry])
  useEffect(() => { heading.current?.focus() }, [index, loading])
  const questions = allQuestions.filter(q => !q.required_when || Object.entries(q.required_when).every(([key, expected]) => answers[allQuestions.find(parent => parent.key === key)?.id ?? -1] === expected))
  useEffect(() => { if (progress) onProgress?.(progress) }, [progress, onProgress])
  const question = questions[index]
  const required = question?.required || !!question?.required_when
  const value = question ? answers[question.id] ?? null : null
  function update(next: AnswerValue) {
    setAnswers(previous => {
      const updated = { ...previous, [question.id]: next }
      for (const child of allQuestions) {
        if (child.required_when?.[question.key] && next !== child.required_when[question.key]) updated[child.id] = null
      }
      return updated
    })
    setError(''); setNotice('')
  }
  async function save(event: FormEvent | null, skip = false) {
    event?.preventDefault(); setError(''); setNotice('')
    const next = skip ? null : value
    const empty = next === null || (typeof next === 'string' && !next.trim()) || (Array.isArray(next) && !next.length)
    if (!skip && empty) { setError(required ? 'Please answer this required question.' : 'Enter an answer or choose Skip question.'); return }
    if (typeof next === 'number' && !Number.isFinite(next)) { setError('Enter a valid number.'); return }
    setSaving(true)
    try {
      await api.saveAnswer(student.id, question.id, next)
      setAnswers(a => ({ ...a, [question.id]: next }))
      setProgress(await api.progress(student.id)); setNotice(skip ? 'Question skipped. Your progress is saved.' : 'Answer saved.')
      if (index < questions.length - 1) setIndex(index + 1)
      else setFinished(true)
    } catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }
  return <><PageTitle eyebrow="STEP BY STEP" title="Let’s start with you.">20 questions · Only 5 required. Skip optional questions and update your answers anytime.</PageTitle>
    {loading ? <Loading text="Loading your questions and saved answers…" /> : !questions.length ? <ErrorNotice error={error || 'No questions are available yet.'} retry={() => { setLoading(true); setRetry(r => r + 1) }} /> : <>
      <div className="assessment-progress"><div className="flex justify-between gap-3"><span>{progress?.answered_questions ?? 0} of {questions.length} answers saved</span><strong>{progress?.completion_percent ?? 0}%</strong></div><progress aria-label="Saved assessment progress" max={100} value={progress?.completion_percent ?? 0} /></div>
      {finished ? <section className="panel completion"><CheckCircle2 size={40} /><h2>Your answers are saved.</h2><p>{progress?.is_complete ? 'All required questions are complete.' : 'Some required questions still need answers.'} You can review and update your profile anytime.</p><button className="button primary" disabled={!progress?.is_complete} onClick={onDone}>View my profile <ArrowRight size={17} /></button><button className="text-button" onClick={() => { setFinished(false); setIndex(0) }}>Review answers</button></section> : <form className="panel question-panel" onSubmit={e => save(e)}>
        <div className="flex justify-between gap-4"><p className="eyebrow">QUESTION {index + 1} OF {questions.length}</p><span className="pill">{required ? 'Required' : 'Optional'}</span></div>
        <h2 ref={heading} tabIndex={-1} id="question-title">{question.prompt}</h2>
        <p className="muted mb-6">{required ? 'This question needs an answer to complete the assessment.' : 'Share what you’re comfortable with, or skip this question.'}</p>
        <fieldset disabled={saving} aria-labelledby="question-title" aria-describedby={error ? 'answer-error' : undefined} aria-invalid={!!error}>
          {question.response_type === 'text' && <textarea aria-label={question.prompt} rows={5} value={typeof value === 'string' ? value : ''} onChange={e => update(e.target.value)} placeholder="Your answer…" />}
          {question.response_type === 'number' && <input aria-label={question.prompt} type="number" step="any" value={typeof value === 'number' ? value : ''} onChange={e => update(e.target.value === '' ? null : Number(e.target.value))} />}
          {question.options.map(option => <label className="choice" key={option}><input name={`question-${question.id}`} type={question.response_type === 'multiple-choice' ? 'checkbox' : 'radio'} checked={Array.isArray(value) ? value.includes(option) : value === option} onChange={e => update(question.response_type === 'multiple-choice' ? e.target.checked ? [...(Array.isArray(value) ? value : []), option] : (Array.isArray(value) ? value : []).filter(v => v !== option) : option)} /><span>{option}</span></label>)}
        </fieldset>
        {error && <div id="answer-error"><ErrorNotice error={error} /></div>}
        <div className="question-actions"><button type="button" className="button secondary" disabled={!index || saving} onClick={() => { setIndex(index - 1); setError(''); setNotice('') }}><ArrowLeft size={16} />Back</button><div className="flex flex-wrap items-center gap-4">{!required && <button type="button" className="text-button" disabled={saving} onClick={() => save(null, true)}>Skip question</button>}<button className="button primary" disabled={saving}>{saving ? 'Saving…' : index === questions.length - 1 ? 'Save & finish' : 'Save & next'}<ArrowRight size={16} /></button></div></div>
      </form>}
      <p className="save-notice" role="status">{notice || 'Answers are saved when you choose Next or Skip. Back keeps unsaved changes only while this page stays open.'}</p>
    </>}
  </>
}
