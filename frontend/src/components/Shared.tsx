import type { ReactNode } from 'react'
import { LoaderCircle, AlertCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

export function Loading({ text = 'Loading your space…' }: { text?: string }) {
  return <p className="status" role="status"><LoaderCircle size={18} aria-hidden="true" />{text}</p>
}
export function ErrorNotice({ error, retry }: { error: string; retry?: () => void }) {
  return <div className="error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}{retry && <button className="text-button block" onClick={retry}>Try again</button>}</div></div>
}
export function PageTitle({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return <header className="page-title"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{children && <p className="subtitle">{children}</p>}</header>
}
export function GuidanceText({ content }: { content: string }) {
  return <div className="guidance-text"><ReactMarkdown components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}>{content}</ReactMarkdown></div>
}
