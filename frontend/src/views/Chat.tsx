import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Leaf, MessageCircle, Plus, Send, UserRound } from 'lucide-react'
import { api, ApiError } from '../api/client'
import type { Conversation, Message, Student } from '../api/types'
import { ErrorNotice, GuidanceText, Loading, PageTitle } from '../components/Shared'

export function Chat({ student, initialConversation }: { student: Student; initialConversation: number | null }) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversation, setConversation] = useState<number | null>(initialConversation)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const bottom = useRef<HTMLDivElement>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const sequence = useRef(0)
  const invalidateRequests = useCallback(() => { sequence.current++ }, [])
  useEffect(() => {
    let active = true
    Promise.all([api.conversations(student.id), initialConversation ? api.conversation(student.id, initialConversation) : Promise.resolve(null)]).then(([list, detail]) => {
      if (active) { setConversations(list); if (detail) setMessages(detail.messages); setLoading(false) }
    }).catch(e => { if (active) { setError(e.message); setLoading(false) } })
    return () => { active = false; invalidateRequests() }
  }, [student.id, initialConversation, invalidateRequests])
  useEffect(() => { bottom.current?.scrollIntoView?.({ block: 'nearest' }) }, [messages, pending])
  async function open(id: number | null) {
    const request = ++sequence.current
    setConversation(id); setError(''); setMessages([]); setDraft('')
    if (!id) { setLoading(false); textarea.current?.focus(); return }
    setLoading(true)
    try { const detail = await api.conversation(student.id, id); if (request === sequence.current) setMessages(detail.messages) }
    catch (e) { if (request === sequence.current) setError((e as Error).message) }
    finally { if (request === sequence.current) setLoading(false) }
  }
  async function reload() {
    const request = ++sequence.current
    setError(''); setLoading(true)
    try {
      const [list, detail] = await Promise.all([api.conversations(student.id), conversation ? api.conversation(student.id, conversation) : Promise.resolve(null)])
      if (request === sequence.current) { setConversations(list); setMessages(detail?.messages ?? []) }
    } catch (e) { if (request === sequence.current) setError((e as Error).message) }
    finally { if (request === sequence.current) setLoading(false) }
  }
  async function send(event: FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || sending || loading) return
    const request = ++sequence.current
    setSending(true); setError(''); setPending(text); setDraft('')
    try {
      const reply = await api.chat(student.id, text, conversation)
      if (request !== sequence.current) return
      setConversation(reply.conversation_id)
      setMessages(old => [...old, reply.student_message, reply.assistant_message])
      try { const list = await api.conversations(student.id); if (request === sequence.current) setConversations(list) }
      catch { if (request === sequence.current) setError('Your reply was saved, but the conversation list could not refresh. Reopen the counselor to refresh it.') }
    } catch (e) {
      if (request !== sequence.current) return
      const failure = e as ApiError
      setError(failure.message)
      if (failure.conversationId) {
        const savedId = failure.conversationId
        setConversation(savedId)
        try {
          const [detail, list] = await Promise.all([api.conversation(student.id, savedId), api.conversations(student.id)])
          if (request === sequence.current) { setMessages(detail.messages); setConversations(list) }
        } catch { if (request === sequence.current) setError(`${failure.message} Reopen this conversation to load its saved messages.`) }
      } else {
        setDraft(text)
        if (failure.status === 0) setError(`${failure.message} The request may have reached the server. Check conversation history before sending again.`)
      }
    } finally { if (request === sequence.current) { setSending(false); setPending(''); textarea.current?.focus() } }
  }
  return <><PageTitle eyebrow="A SPACE TO THINK OUT LOUD" title="Your AI guidance counselor.">No perfect questions needed. Let’s explore your next step together.</PageTitle>
    <div className="chat-layout"><aside className="conversation-sidebar panel"><button className="button secondary w-full" disabled={sending || loading} onClick={() => open(null)}><Plus size={17} />New conversation</button><h2>YOUR CONVERSATIONS</h2><div className="conversation-list">{[...conversations].reverse().map((c, i) => <button key={c.id} disabled={sending || loading} aria-pressed={conversation === c.id} onClick={() => open(c.id)}><MessageCircle size={17} /><span>Conversation {conversations.length - i}<small>{new Date(c.created_at).toLocaleDateString()}</small></span></button>)}{!loading && !conversations.length && <p className="muted text-sm">Your conversations will appear here.</p>}</div></aside>
      <section className="chat-main panel" aria-label="Guidance conversation"><div className="chat-heading"><span className="brand-mark small"><Leaf size={20} /></span><div><strong>PathBridge counselor</strong><small>AI-powered · Here to help you explore</small></div></div>
        <div className="chat-transcript" aria-live="polite" aria-relevant="additions text" aria-busy={loading || sending}>
          {loading && <Loading text="Loading your conversations…" />}
          {!loading && !messages.length && !pending && <div className="chat-empty"><span className="empty-icon"><MessageCircle size={32} /></span><h2>What’s on your mind?</h2><p>Explore an interest, talk about an obstacle, or ask where to start.</p><div className="suggestions">{['How can I explore my career interests?', 'How can I try programming with limited equipment?'].map(s => <button key={s} onClick={() => { setDraft(s); textarea.current?.focus() }}>{s}</button>)}</div></div>}
          {messages.map(message => <article key={message.id} className={`message ${message.role}`} aria-label={`${message.role === 'user' ? 'You' : 'Counselor'} message`}><span className="message-avatar">{message.role === 'user' ? <UserRound size={17} /> : <Leaf size={18} />}</span><div><strong>{message.role === 'user' ? 'You' : 'PathBridge counselor'}</strong><GuidanceText content={message.content} />{message.status !== 'completed' && <small className="message-status">{message.status === 'failed' ? 'Saved · Reply unavailable' : 'Saved · Awaiting a reply'}</small>}</div></article>)}
          {pending && <article className="message user"><span className="message-avatar"><UserRound size={17} /></span><div><strong>You</strong><p className="whitespace-pre-wrap">{pending}</p><Loading text="Thinking through your question…" /></div></article>}
          <div ref={bottom} />
        </div>
        {error && <ErrorNotice error={error} retry={!sending ? reload : undefined} />}
        <form className="chat-composer" onSubmit={send}><label className="sr-only" htmlFor="chat-message">Your message</label><textarea ref={textarea} id="chat-message" rows={2} maxLength={4000} value={draft} disabled={sending || loading} onChange={e => setDraft(e.target.value)} placeholder="Ask a question or share what’s on your mind…" /><div className="flex items-center justify-between gap-3"><span>{draft.length}/4000 · Avoid personal identifying details</span><button className="button primary" disabled={sending || loading || !draft.trim()} type="submit">{sending ? 'Sending…' : 'Send'}<Send size={16} /></button></div></form>
      </section></div>
    <aside className="evidence-note"><strong>Explore ideas. Check the evidence.</strong> Source references appear within replies when available. General suggestions are starting points; verify requirements, costs, and eligibility with official sources and a human counselor.</aside>
  </>
}
