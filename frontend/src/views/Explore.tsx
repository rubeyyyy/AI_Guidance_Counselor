import { useEffect, useState } from 'react'
import { ArrowRight, Compass } from 'lucide-react'
import { api } from '../api/client'
import type { ConversationDetail, Student } from '../api/types'
import { ErrorNotice, GuidanceText, Loading, PageTitle } from '../components/Shared'

export function Explore({ student, onChat, onOpen }: { student: Student; onChat: () => void; onOpen: (id: number) => void }) {
  const [details, setDetails] = useState<ConversationDetail[] | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    api.conversations(student.id).then(async conversations => {
      // Load sequentially to avoid a burst of requests for long-lived student records.
      const result: ConversationDetail[] = []
      for (const conversation of [...conversations].reverse()) {
        if (!active) return
        result.push(await api.conversation(student.id, conversation.id))
      }
      if (active) setDetails(result)
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [student.id, retry])
  const replies = details?.flatMap(c => c.messages.filter(m => m.role === 'assistant' && m.status === 'completed').map(message => ({ conversation: c.id, message, question: c.messages.find(m => m.id === message.reply_to_message_id)?.content })))
  return <><PageTitle eyebrow="KEEP YOUR CURIOSITY GOING" title="Your pathway notebook.">Revisit guidance from your conversations and decide what you’d like to explore next.</PageTitle><div className="sample-notice">These are saved counselor replies, not a ranked career recommendation list. Source references and important limitations are preserved in the original text.</div>
    {error ? <ErrorNotice error={error} retry={() => { setError(''); setRetry(r => r + 1) }} /> : !details ? <Loading text="Gathering your past guidance…" /> : !replies?.length ? <section className="panel completion"><Compass size={40} /><h2>A world of possibilities starts with a question.</h2><p>Talk with your counselor first. Your saved guidance will appear here.</p><button className="button primary" onClick={onChat}>Explore with my counselor <ArrowRight size={16} /></button></section> : <div className="space-y-5">{replies.map(({ conversation, message, question }) => <article className="panel exploration-card" key={message.id}><p className="eyebrow">FROM YOUR CONVERSATION · {new Date(message.created_at).toLocaleDateString()}</p><h2>{question || 'Saved guidance'}</h2><GuidanceText content={message.content} /><button className="text-button mt-5" onClick={() => onOpen(conversation)}>Continue this conversation <ArrowRight size={15} /></button></article>)}</div>}
  </>
}
