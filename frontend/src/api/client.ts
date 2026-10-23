import type { Answer, AnswerValue, ChatResponse, Conversation, ConversationDetail, Profile, Progress, Question, Student } from './types'

export interface AuthUser { id: number; email: string; role: 'student' | 'counselor'; student_id: number | null; is_active: boolean; email_verified: boolean }
let csrfToken = ''
let csrfPending: Promise<void> | null = null
export function clearCsrf() { csrfToken = '' }
async function ensureCsrf() {
  if (csrfToken) return
  if (!csrfPending) csrfPending = request<{ csrf_token: string }>('/auth/csrf').then(data => { csrfToken = data.csrf_token }).finally(() => { csrfPending = null })
  await csrfPending
}

export const QUESTIONNAIRE = 'initial-v2'
const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
export class ApiError extends Error {
  constructor(message: string, public status: number, public conversationId?: number) { super(message) }
}
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = options?.method || 'GET'
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) await ensureCsrf()
  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...options, credentials: 'include', headers: { 'Content-Type': 'application/json', ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}), ...options?.headers }, cache: 'no-store' })
  } catch { throw new ApiError('Cannot reach PathBridge. Check your connection and that the API server is running.', 0) }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    const message = typeof detail === 'string' ? detail : typeof detail?.message === 'string' ? detail.message
      : Array.isArray(detail) ? detail.map((e: { msg?: string }) => e.msg || 'Invalid value').join('. ')
      : `Request failed (${response.status}). Please try again.`
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('pathbridge:session-expired'))
    if (response.status === 403) clearCsrf()
    throw new ApiError(message, response.status, typeof detail?.conversation_id === 'number' ? detail.conversation_id : undefined)
  }
  return response.json() as Promise<T>
}
const assessment = (id: number) => `/students/${id}/assessments/${QUESTIONNAIRE}`
export const api = {
  me: () => request<AuthUser>('/auth/me'),
  startRegistration: (email: string, password: string, display_name?: string) => request<{ message: string; challenge_id: string }>('/auth/register', {
    method: 'POST', body: JSON.stringify({ email, password, display_name: display_name?.trim() || null }),
  }),
  verifyEmail: async (challenge_id: string, code: string) => {
    const result = await request<{ user: AuthUser; csrf_token: string }>('/auth/verify-email', {
      method: 'POST', body: JSON.stringify({ challenge_id, code }),
    })
    csrfToken = result.csrf_token
    return result.user
  },
  resendVerification: (email: string, challenge_id: string) => request<{ message: string }>('/auth/resend-verification', {
    method: 'POST', body: JSON.stringify({ email, challenge_id }),
  }),
  forgotPassword: (email: string) => request<{ message: string; challenge_id: string }>('/auth/forgot-password', {
    method: 'POST', body: JSON.stringify({ email }),
  }),
  resendReset: (email: string, challenge_id: string) => request<{ message: string }>('/auth/resend-reset', {
    method: 'POST', body: JSON.stringify({ email, challenge_id }),
  }),
  resetPassword: async (challenge_id: string, code: string, new_password: string) => {
    const result = await request<{ message: string }>('/auth/reset-password', {
      method: 'POST', body: JSON.stringify({ challenge_id, code, new_password }),
    })
    clearCsrf()
    return result
  },
  authenticate: async (_mode: 'login', email: string, password: string) => {
    const result = await request<{ user: AuthUser; csrf_token: string }>('/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password }),
    })
    csrfToken = result.csrf_token
    return result.user
  },
  logout: async () => { await request('/auth/logout', { method: 'POST' }); clearCsrf() },
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
