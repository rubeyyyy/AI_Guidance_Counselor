import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { api, ApiError } from '../api/client'
import type { AnswerValue, ConversationDetail, Message, Question } from '../api/types'
import { GuidanceText } from '../components/Shared'

const questions: Question[] = [
  { id: 11, key: 'sample_text', prompt: 'A dynamic text question', response_type: 'text', required: true, options: [], display_order: 1 },
  { id: 12, key: 'sample_number', prompt: 'A dynamic number question', response_type: 'number', required: true, options: [], display_order: 2 },
  { id: 13, key: 'sample_choice', prompt: 'A dynamic choice question', response_type: 'single-choice', required: false, options: ['One', 'Two'], display_order: 3 },
  { id: 14, key: 'sample_choices', prompt: 'A dynamic multiple question', response_type: 'multiple-choice', required: false, options: ['Alpha', 'Beta'], display_order: 4 },
]
const student = { id: 42, display_name: 'Practice', created_at: '2026-01-01T00:00:00Z' }
let values: Record<number, AnswerValue>
let conversation: ConversationDetail | null
let failure: { path: string; status: number; detail: unknown } | null
let fetchMock: ReturnType<typeof vi.fn>
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
function progress() {
  const count = Object.values(values).filter(v => v !== null).length
  return { total_questions: 4, answered_questions: count, required_questions: 2, answered_required_questions: [11, 12].filter(id => values[id] != null).length, completion_percent: count * 25, is_complete: values[11] != null && values[12] != null }
}
beforeEach(() => {
  values = {}; conversation = null; failure = null
  fetchMock = vi.fn(async (input: string, options: RequestInit = {}) => {
    const path = new URL(input).pathname
    if (failure && path.endsWith(failure.path)) return response({ detail: failure.detail }, failure.status)
    if (path === '/students' && options.method === 'POST') return response(student, 201)
    if (path === '/students/42') return response(student)
    if (path === '/students/999') return response({ detail: 'Student not found' }, 404)
    if (path.endsWith('/questions')) return response(questions)
    if (path.endsWith('/answers')) return response(Object.entries(values).map(([id, value]) => ({ question_id: Number(id), value })))
    if (/\/answers\/\d+$/.test(path) && options.method === 'PUT') {
      const id = Number(path.split('/').at(-1)); const { value } = JSON.parse(String(options.body))
      values[id] = value
      return response({ question_id: id, value })
    }
    if (path.endsWith('/progress')) return response(progress())
    if (path.endsWith('/profile')) return response({ student_id: 42, display_name: 'Practice', questionnaire_id: 'sample-initial-v1', is_sample: true, fields: questions.map(q => ({ key: q.key, question_id: q.id, value: values[q.id] ?? null })), progress: progress() })
    if (path.endsWith('/conversations')) return response(conversation ? [{ ...conversation, messages: undefined }] : [])
    if (path.endsWith('/conversations/7') && conversation) return response(conversation)
    if (path.endsWith('/chat') && options.method === 'POST') {
      const payload = JSON.parse(String(options.body))
      const start = conversation?.messages.length ?? 0
      const user: Message = { id: start + 1, role: 'user', content: payload.message, status: 'completed', reply_to_message_id: null, created_at: student.created_at }
      const assistant: Message = { ...user, id: start + 2, role: 'assistant', reply_to_message_id: user.id, content: 'SAMPLE exploratory guidance [sample-programming]. Check [the source](https://example.org/guide) with a counselor.' }
      conversation = { id: 7, student_id: 42, questionnaire_id: 'sample-initial-v1', created_at: student.created_at, messages: [...(conversation?.messages ?? []), user, assistant] }
      return response({ conversation_id: 7, student_message: user, assistant_message: assistant })
    }
    throw new Error(`Unmocked API request: ${options.method || 'GET'} ${path}`)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())
async function enter() {
  const user = userEvent.setup()
  render(<App />)
  await user.click(screen.getByRole('button', { name: 'Create student' }))
  await screen.findByText(/Selected student #42/)
  return user
}

describe('student workflow with mocked HTTP responses', () => {
  it('creates a student with the real contract and keeps data out of browser storage', async () => {
    const user = userEvent.setup(); render(<App />)
    await user.type(screen.getByLabelText(/Fictional display name/), 'Practice')
    await user.click(screen.getByRole('button', { name: 'Create student' }))
    await screen.findByText(/Selected student #42/)
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ display_name: 'Practice' })
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0)
  })
  it('loads a known ID and reports missing students', async () => {
    const user = userEvent.setup(); render(<App />)
    const input = screen.getByLabelText(/existing development student ID/)
    await user.type(input, '999'); await user.click(screen.getByRole('button', { name: 'Load student' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Student not found')
    await user.clear(input); await user.type(input, '42'); await user.click(screen.getByRole('button', { name: 'Load student' }))
    await screen.findByText(/Selected student #42/)
  })
  it('loads dynamic questions, validates, saves all types, skips and edits answers', async () => {
    const user = await enter()
    await user.click(screen.getByRole('button', { name: 'Initial assessment' }))
    const text = await screen.findByRole('textbox', { name: questions[0].prompt })
    await user.click(screen.getByRole('button', { name: 'Save & next' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('required')
    await user.type(text, 'Practice answer'); await user.click(screen.getByRole('button', { name: 'Save & next' }))
    await user.type(await screen.findByRole('spinbutton', { name: questions[1].prompt }), '3.5')
    await user.click(screen.getByRole('button', { name: 'Save & next' }))
    await user.click(await screen.findByRole('radio', { name: 'One' }))
    await user.click(screen.getByRole('button', { name: 'Save & next' }))
    await user.click(await screen.findByRole('checkbox', { name: 'Alpha' }))
    await user.click(screen.getByRole('checkbox', { name: 'Beta' }))
    await user.click(screen.getByRole('button', { name: 'Save & finish' }))
    await screen.findByText('Your answers are saved.')
    expect(values).toEqual({ 11: 'Practice answer', 12: 3.5, 13: 'One', 14: ['Alpha', 'Beta'] })
    await user.click(screen.getByRole('button', { name: 'View my profile' }))
    expect(await screen.findByText('Practice answer')).toBeVisible()
    expect(screen.getAllByText('Not provided by the current questionnaire.')).toHaveLength(8)
    await user.click(screen.getByRole('button', { name: 'Edit assessment' }))
    const saved = await screen.findByRole('textbox', { name: questions[0].prompt })
    expect(saved).toHaveValue('Practice answer')
    await user.clear(saved); await user.type(saved, 'Edited answer')
    await user.click(screen.getByRole('button', { name: 'Save & next' }))
    await screen.findByRole('spinbutton'); expect(values[11]).toBe('Edited answer')
    await user.click(screen.getByRole('button', { name: 'Save & next' }))
    await user.click(await screen.findByRole('button', { name: 'Skip question' }))
    await screen.findByRole('checkbox', { name: 'Alpha' }); expect(values[13]).toBeNull()
  })
  it('resumes saved progress and retains input when saving fails', async () => {
    values = { 11: 'Previously saved' }
    const user = await enter(); await user.click(screen.getByRole('button', { name: 'Initial assessment' }))
    await user.type(await screen.findByRole('spinbutton'), '9')
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '25')
    failure = { path: '/answers/12', status: 422, detail: 'Answer does not match question type' }
    await user.click(screen.getByRole('button', { name: 'Save & next' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Answer does not match')
    expect(screen.getByRole('spinbutton')).toHaveValue(9)
    failure = null
    await user.click(screen.getByRole('button', { name: 'Save & next' }))
    await screen.findByRole('radio', { name: 'One' })
    await user.click(screen.getByRole('button', { name: 'My profile' }))
    await screen.findByText('Previously saved')
    await user.click(screen.getByRole('button', { name: 'Edit assessment' }))
    await screen.findByRole('radio', { name: 'One' })
  })
  it('retries failed questionnaire loading', async () => {
    failure = { path: '/questions', status: 503, detail: 'Temporarily unavailable' }
    const user = await enter(); await user.click(screen.getByRole('button', { name: 'Initial assessment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Temporarily unavailable')
    failure = null; await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByRole('textbox', { name: questions[0].prompt })
  })
  it('sends messages, continues history, starts new conversations and explores saved guidance', async () => {
    const user = await enter(); await user.click(screen.getByRole('button', { name: 'AI counselor' }))
    const composer = await screen.findByRole('textbox', { name: 'Your message' })
    await waitFor(() => expect(composer).toBeEnabled())
    await user.type(composer, 'I want to explore programming'); await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('link', { name: 'the source' })).toHaveAttribute('href', 'https://example.org/guide')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).not.toHaveTextContent('Sending'))
    await user.type(composer, 'What next?'); await user.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(screen.getAllByRole('link', { name: 'the source' })).toHaveLength(2))
    const calls = fetchMock.mock.calls.filter(c => c[0].endsWith('/chat'))
    expect(JSON.parse(calls[0][1].body as string).conversation_id).toBeNull()
    expect(JSON.parse(calls[1][1].body as string).conversation_id).toBe(7)
    await waitFor(() => expect(screen.getByRole('button', { name: 'New conversation' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(screen.queryByRole('link', { name: 'the source' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Conversation 1/ }))
    await screen.findByText('What next?')
    await user.click(screen.getByRole('button', { name: 'Explore pathways' }))
    await screen.findByRole('heading', { name: 'Your pathway notebook.' })
    expect(await screen.findAllByRole('link', { name: 'the source' })).toHaveLength(2)
    expect(screen.getByText(/not a ranked career recommendation/)).toBeVisible()
    await user.click(screen.getAllByRole('button', { name: 'Continue this conversation' })[0])
    await screen.findByText('What next?')
  })
  it('recovers a provider failure using its saved conversation ID', async () => {
    const user = await enter(); await user.click(screen.getByRole('button', { name: 'AI counselor' }))
    const composer = await screen.findByRole('textbox', { name: 'Your message' })
    await waitFor(() => expect(composer).toBeEnabled())
    conversation = { id: 7, student_id: 42, questionnaire_id: 'sample-initial-v1', created_at: student.created_at, messages: [{ id: 1, role: 'user', content: 'Help me', status: 'failed', reply_to_message_id: null, created_at: student.created_at }] }
    failure = { path: '/chat', status: 502, detail: { message: 'Guidance is unavailable. Your message was saved.', conversation_id: 7, student_message_id: 1 } }
    await user.type(composer, 'Help me'); await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your message was saved')
    expect(await screen.findByText('Saved · Reply unavailable')).toBeVisible()
    await waitFor(() => expect(composer).toBeEnabled())
    failure = null; await user.type(composer, 'Try another question'); await user.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByRole('link', { name: 'the source' })
    const calls = fetchMock.mock.calls.filter(c => c[0].endsWith('/chat'))
    expect(JSON.parse(calls[1][1].body as string).conversation_id).toBe(7)
  })
  it('shows empty exploration without fabricating careers', async () => {
    const user = await enter(); await user.click(screen.getByRole('button', { name: 'Explore pathways' }))
    await screen.findByText('A world of possibilities starts with a question.')
  })
})

it('handles network errors without exposing credentials', async () => {
  fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
  await expect(api.student(42)).rejects.toBeInstanceOf(ApiError)
})
it('renders reference text without executing HTML or unsafe URLs', () => {
  const { container } = render(<GuidanceText content={'SAMPLE [doc-id]\n\n[unsafe](javascript:alert(1))\n\n<script>alert(1)</script>'} />)
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('a')).not.toHaveAttribute('href', 'javascript:alert(1)')
  expect(screen.getByText(/SAMPLE/)).toBeVisible()
})
