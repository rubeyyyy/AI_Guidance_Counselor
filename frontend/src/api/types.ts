export type AnswerValue = string | number | string[] | null
export interface Student { id: number; display_name: string | null; created_at: string }
export interface Question {
  id: number; key: string; prompt: string; required: boolean; display_order: number
  required_when?: Record<string, string> | null
  response_type: 'text' | 'number' | 'single-choice' | 'multiple-choice'; options: string[]
}
export interface Answer { question_id: number; value: AnswerValue }
export interface Progress {
  total_questions: number; answered_questions: number; required_questions: number
  answered_required_questions: number; completion_percent: number; is_complete: boolean
}
export interface Profile {
  student_id: number; display_name: string | null; questionnaire_id: string; is_sample: boolean
  fields: { key: string; question_id: number; value: AnswerValue }[]; progress: Progress
}
export interface Message {
  id: number; role: 'user' | 'assistant'; content: string; status: 'pending' | 'completed' | 'failed'
  reply_to_message_id: number | null; created_at: string
}
export interface Conversation { id: number; student_id: number; questionnaire_id: string; created_at: string }
export interface ConversationDetail extends Conversation { messages: Message[] }
export interface ChatResponse { conversation_id: number; student_message: Message; assistant_message: Message }
