import type { Answer, AnswerValue, ChatResponse, Conversation, ConversationDetail, Profile, Progress, Question, Student } from './types'

export const QUESTIONNAIRE = 'sample-initial-v1'
const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
export class ApiError extends Error {
  constructor(message: string, public status: number, public conversationId?: number) { super(message) }
}
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers }, cache: 'no-store' })
  } catch { throw new ApiError('Cannot reach PathBridge. Check your connection and that the API server is running.', 0) }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    const message = typeof detail === 'string' ? detail : typeof detail?.message === 'string' ? detail.message
      : Array.isArray(detail) ? detail.map((e: { msg?: string }) => e.msg || 'Invalid value').join('. ')
      : `Request failed (${response.status}). Please try again.`
    throw new ApiError(message, response.status, typeof detail?.conversation_id === 'number' ? detail.conversation_id : undefined)
  }
  return response.json() as Promise<T>
}
const assessment = (id: number) => `/students/${id}/assessments/${QUESTIONNAIRE}`
export const api = {
  createStudent: (name: string) => request<Student>('/students', { method: 'POST', body: JSON.stringify({ display_name: name.trim() || null }) }),
  student: (id: number) => request<Student>(`/students/${id}`),
  questions: () => request<Question[]>(`/questionnaires/${QUESTIONNAIRE}/questions`),
  answers: (id: number) => request<Answer[]>(`${assessment(id)}/answers`),
  progress: (id: number) => request<Progress>(`${assessment(id)}/progress`),
  profile: (id: number) => request<Profile>(`${assessment(id)}/profile`),
  saveAnswer: (id: number, question: number, value: AnswerValue) => request<Answer>(`${assessment(id)}/answers/${question}`, { method: 'PUT', body: JSON.stringify({ value }) }),
  conversations: (id: number) => request<Conversation[]>(`/students/${id}/conversations`),
  conversation: (id: number, conversation: number) => request<ConversationDetail>(`/students/${id}/conversations/${conversation}`),
  chat: (id: number, message: string, conversation: number | null) => request<ChatResponse>(`/students/${id}/chat`, { method: 'POST', body: JSON.stringify({ message, conversation_id: conversation }) }),
}
