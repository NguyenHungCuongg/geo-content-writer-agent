import { useState } from 'react'
import type { ReactNode } from 'react'
import type { Article, Citation } from './api'

// Cùng quy tắc tách câu với agent/article.py: dấu kết câu, khoảng trắng, rồi chữ hoa hoặc chữ số.
const SENTENCE_END = /(?<=[.!?…])\s+(?=["“([]?[A-ZÀ-Ỹ0-9])/u
const CITE = /\[(\d+)\]/g
const TABLE_SEPARATOR = /^\|?\s*:?-{3,}/
const LIST_MARKER = /^\s*(?:[-*+]|\d+[.)])\s+/

const stripInline = (text: string) => text.replace(/\*\*|__|`/g, '')

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
        return (
          <span key={i}>
            <mark
              className={`cited${ns.includes(selected ?? -1) ? ' active' : ''}`}
              role="button"
              tabIndex={0}
              title="Bấm để xem nguồn"
              onClick={() => onSelect(ns[0])}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(ns[0])}
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

export function ArticleView({ article }: { article: Article }) {
  const [selected, setSelected] = useState<number | null>(null)
  const { outline } = article
  const citations = new Map(article.citations.map((c) => [c.n, c]))
  const current = selected === null ? undefined : citations.get(selected)
  const cited = (text: string) => (
    <CitedText text={text} citations={citations} selected={selected} onSelect={setSelected} />
  )

  const rendered: ReactNode[] = parseBlocks(article.markdown).map((b, i) => {
    switch (b.kind) {
      case 'heading': {
        const Tag = `h${Math.min(b.level + 1, 6)}` as 'h2'
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
    <section>
      <h2>Dàn ý GEO</h2>
      <div className="box">
        <p><strong>{outline.title}</strong></p>
        <p className="muted">{outline.meta_description}</p>
        <p>
          Từ khoá chính: <code>{outline.primary_keyword}</code>
          {outline.secondary_keywords.length > 0 && <> · phụ: {outline.secondary_keywords.join(', ')}</>}
        </p>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Mục</th><th>Trả lời trước (answer-first)</th><th>Định dạng</th><th>Prompt</th></tr>
            </thead>
            <tbody>
              {outline.sections.map((s, i) => (
                <tr key={i}>
                  <td>{s.level === 3 ? '↳ ' : ''}{s.heading}</td>
                  <td>{s.answer_first}</td>
                  <td>{s.format}{s.needs_citation ? ' · cần nguồn' : ''}</td>
                  <td>{s.prompt_ids.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <details>
          <summary>FAQ ({outline.faq.length} câu)</summary>
          <ul>{outline.faq.map((f, i) => <li key={i}><strong>{f.question}</strong> {f.answer}</li>)}</ul>
        </details>
      </div>

      {article.notes.length > 0 && (
        <div className="box warning">
          <h3>Ghi chú của agent</h3>
          <ul>{article.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </div>
      )}

      <h2>Bài viết</h2>
      <p className="muted">
        Câu tô vàng có trích dẫn. Bấm vào câu để xem URL và đoạn trích nguồn ({article.citations.length} trích dẫn).
      </p>
      <div className="article-layout">
        <article className="article-body">{rendered}</article>
        <aside className="citation-panel" aria-live="polite">
          {current ? (
            <>
              <h3>Nguồn [{current.n}]</h3>
              <p><a href={current.url} target="_blank" rel="noreferrer">{current.url}</a></p>
              <blockquote>{current.quote}</blockquote>
              <p className="muted">chunk: <code>{current.chunk_id}</code></p>
            </>
          ) : (
            <p className="muted">Chưa chọn câu nào.</p>
          )}
          <h3>Tất cả trích dẫn</h3>
          <ol className="citation-list">
            {article.citations.map((c) => (
              <li key={c.n}>
                <button type="button" className="link" onClick={() => setSelected(c.n)}>[{c.n}]</button>{' '}
                {new URL(c.url, 'http://x').hostname}
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </section>
  )
}
