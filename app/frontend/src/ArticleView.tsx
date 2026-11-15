import { useState } from 'react'
import type { ReactNode } from 'react'
import type { Article, Citation } from './api'
import { AlertIcon } from './Icons'

// Cùng quy tắc tách câu với agent/article.py: dấu kết câu, khoảng trắng, rồi chữ hoa hoặc chữ số.
const SENTENCE_END = /(?<=[.!?…])\s+(?=["“([]?[A-ZÀ-Ỹ0-9])/u
const CITE = /\[(\d+)\]/g
const TABLE_SEPARATOR = /^\|?\s*:?-{3,}/
const LIST_MARKER = /^\s*(?:[-*+]|\d+[.)])\s+/

const stripInline = (text: string) => text.replace(/\*\*|__|`/g, '')

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname || url
  } catch {
    return url
  }
}

type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'table'; rows: string[][] }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'paragraph'; text: string }

/** Markdown tối giản đủ cho bài UC-03: heading, đoạn, danh sách, bảng. */
function parseBlocks(markdown: string): Block[] {
  const blocks: Block[] = []
  for (const chunk of markdown.split(/\n\s*\n/)) {
    const lines = chunk.split('\n').map((l) => l.trim()).filter(Boolean)
    if (!lines.length) continue
    const heading = lines[0].match(/^(#{1,6})\s+(.*?)\s*#*$/)
    if (heading) {
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2] })
      if (lines.length > 1) blocks.push({ kind: 'paragraph', text: lines.slice(1).join(' ') })
    } else if (lines[0].startsWith('|')) {
      const rows = lines
        .filter((l) => !TABLE_SEPARATOR.test(l))
        .map((l) => l.replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
      blocks.push({ kind: 'table', rows })
    } else if (lines.every((l) => LIST_MARKER.test(l))) {
      blocks.push({
        kind: 'list',
        ordered: /^\d/.test(lines[0]),
        items: lines.map((l) => l.replace(LIST_MARKER, '')),
      })
    } else {
      blocks.push({ kind: 'paragraph', text: lines.join(' ') })
    }
  }
  return blocks
}

function CitedText({
  text,
  citations,
  selected,
  onSelect,
}: {
  text: string
  citations: Map<number, Citation>
  selected: number | null
  onSelect: (n: number) => void
}) {
  const parts = stripInline(text).split(SENTENCE_END)
  return (
    <>
      {parts.map((sentence, i) => {
        const ns = [...sentence.matchAll(CITE)].map((m) => Number(m[1])).filter((n) => citations.has(n))
        const spacer = i < parts.length - 1 ? ' ' : ''
        if (!ns.length) return <span key={i}>{sentence}{spacer}</span>
        const isActive = ns.includes(selected ?? -1)
        return (
          <span key={i}>
            <mark
              className={`cited${isActive ? ' active' : ''}`}
              role="button"
              tabIndex={0}
              aria-pressed={isActive}
              title="Bấm để xem nguồn"
              onClick={() => onSelect(ns[0])}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect(ns[0])
                }
              }}
            >
              {sentence}
            </mark>
            {spacer}
          </span>
        )
      })}
    </>
  )
}

export function ArticleView({
  article,
  baseHeadingLevel = 2,
}: {
  article: Article
  baseHeadingLevel?: 2 | 3
}) {
  const [selected, setSelected] = useState<number | null>(null)
  const { outline } = article
  const citations = new Map(article.citations.map((c) => [c.n, c]))
  const current = selected === null ? undefined : citations.get(selected)
  const SectionHeading = baseHeadingLevel === 3 ? 'h3' : 'h2'
  const SubHeading = baseHeadingLevel === 3 ? 'h4' : 'h3'
  const cited = (text: string) => (
    <CitedText text={text} citations={citations} selected={selected} onSelect={setSelected} />
  )

  const rendered: ReactNode[] = parseBlocks(article.markdown).map((b, i) => {
    switch (b.kind) {
      case 'heading': {
        const Tag = `h${Math.min(Math.max(b.level, 2) + baseHeadingLevel - 1, 6)}` as 'h3'
        return <Tag key={i}>{stripInline(b.text)}</Tag>
      }
      case 'table':
        return (
          <div className="scroll" key={i}>
            <table>
              <thead><tr>{b.rows[0].map((c, j) => <th key={j}>{cited(c)}</th>)}</tr></thead>
              <tbody>
                {b.rows.slice(1).map((row, r) => (
                  <tr key={r}>{row.map((c, j) => <td key={j}>{cited(c)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      case 'list': {
        const items = b.items.map((item, j) => <li key={j}>{cited(item)}</li>)
        return b.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>
      }
      default:
        return <p key={i}>{cited(b.text)}</p>
    }
  })

  return (
    <section className="section-block">
      <SectionHeading>Dàn ý GEO</SectionHeading>
      <div className="section-block">
        <div>
          <SubHeading>{outline.title}</SubHeading>
          <p className="muted">{outline.meta_description}</p>
        </div>
        <div className="tag-group">
          <span>Từ khoá chính: <code>{outline.primary_keyword}</code></span>
          {outline.secondary_keywords.length > 0 && (
            <span className="muted">Phụ: {outline.secondary_keywords.join(', ')}</span>
          )}
        </div>
        <div className="scroll">
          <table className="responsive-table">
            <thead>
              <tr><th>Mục</th><th>Trả lời trước (answer-first)</th><th>Định dạng</th><th>Prompt</th></tr>
            </thead>
            <tbody>
              {outline.sections.map((s, i) => (
                <tr key={i}>
                  <td data-label="Mục">{s.level === 3 ? '  ' : ''}{s.heading}</td>
                  <td data-label="Trả lời trước">{s.answer_first}</td>
                  <td data-label="Định dạng">
                    <span className="tag-group">
                      <span className="badge">{s.format}</span>
                      {s.needs_citation && <span className="badge">cần nguồn</span>}
                    </span>
                  </td>
                  <td data-label="Prompt" className="num">{s.prompt_ids.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <details>
          <summary>FAQ ({outline.faq.length} câu)</summary>
          <ul className="inline-list">
            {outline.faq.map((f, i) => (
              <li key={i}><strong>{f.question}</strong> {f.answer}</li>
            ))}
          </ul>
        </details>
      </div>

      {article.notes.length > 0 && (
        <div className="alert alert--warning">
          <div className="alert__head">
            <AlertIcon />
            <SubHeading>Ghi chú của agent</SubHeading>
          </div>
          <ul className="inline-list">{article.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </div>
      )}

      <div className="section-block">
        <div>
          <SectionHeading>Bài viết</SectionHeading>
          <p className="muted">
            Câu tô sáng có trích dẫn. Bấm vào câu để xem URL và đoạn trích nguồn (<span className="num">{article.citations.length}</span> trích dẫn).
          </p>
        </div>
        <div className="article-layout">
          <article className="article-body">{rendered}</article>
          <aside className="citation-panel ticks" aria-live="polite">
            {current ? (
              <>
                <SubHeading>Nguồn [{current.n}]</SubHeading>
                <p><a href={current.url} target="_blank" rel="noreferrer" className="url-break">{current.url}</a></p>
                <blockquote>{current.quote}</blockquote>
                <p className="muted">chunk: <code className="num">{current.chunk_id}</code></p>
              </>
            ) : (
              <p className="muted">Chưa chọn câu nào.</p>
            )}
            <SubHeading>Tất cả trích dẫn</SubHeading>
            <ol className="citation-list">
              {article.citations.map((c) => (
                <li key={c.n}>
                  <button type="button" className="link num" onClick={() => setSelected(c.n)}>[{c.n}]</button>
                  <span>{safeHostname(c.url)}</span>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      </div>
    </section>
  )
}
