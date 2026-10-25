import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { startRun, watchRun } from './api'
import type { BrandProfile, PromptSet, TraceEvent } from './api'
import { ProfileView, PromptTable } from './Results'

type Status = 'idle' | 'running' | 'done' | 'failed'

const ERROR_TITLES: Record<string, string> = {
  InputError: 'Đầu vào chưa hợp lệ',
  ConfigError: 'Server thiếu cấu hình',
  llm_error: 'Không gọi được Gemini',
  max_iterations: 'Agent dừng giữa chừng',
  loop_detected: 'Agent dừng giữa chừng',
  repair_failed: 'Agent dừng giữa chừng',
}

/** Một dòng tiếng Việt cho mỗi trace event (event do agent/loop.py và agent/uc01.py ghi). */
function describeEvent(e: TraceEvent): string {
  const d = e as Record<string, any>
  switch (e.event) {
    case 'input':
      return `Nhận brief (${d.brief.length} ký tự), chủ đề: ${d.topics.join(', ')}`
    case 'llm_call':
      return `Gọi ${d.model}${d.structured ? ' (chốt kết quả JSON)' : ''}: ` +
        `${d.input_tokens} token vào, ${d.output_tokens} token ra`
    case 'tool_call':
      return `Tool ${d.name}: ${d.ok ? 'xong' : 'lỗi: ' + d.error} (${d.duration_ms} ms)`
    case 'skill_invocation':
      return `Dùng skill ${d.name}`
    case 'decision':
      if (d.action === 'repair') return `Output sai schema, yêu cầu sửa lần ${d.attempt}: ${d.error}`
      if (d.action === 'skip_skill') return `Bỏ qua skill: ${d.reason}`
      return `Quyết định: ${d.action}`
    case 'error':
      return `Lỗi (${d.reason}): ${d.message}`
    case 'output':
      return `Xong: ${d.prompt_set.prompts.length} prompt`
    default:
      return e.event
  }
}

export default function App() {
  const [brief, setBrief] = useState('')
  const [topics, setTopics] = useState(['', '', ''])
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [notice, setNotice] = useState<string | null>(null)
  const closeRun = useRef<(() => void) | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    closeRun.current?.()
    setEvents([])
    setRunId(null)
    setNotice(null)
    setStatus('running')
    try {
      const id = await startRun(brief, topics.filter((t) => t.trim()))
      setRunId(id)
      closeRun.current = watchRun(
        id,
        (event) => {
          setEvents((prev) => [...prev, event])
          if (event.event === 'output') setStatus('done')
          if (event.event === 'error') setStatus('failed')
        },
        () => {
          setNotice(`Mất kết nối tới run ${id}.`)
          setStatus('failed')
        },
      )
    } catch (err) {
      setNotice((err as Error).message)
      setStatus('failed')
    }
  }

  const output = events.find((e) => e.event === 'output')
  const error = events.find((e) => e.event === 'error')

  return (
    <main>
      <h1>GEO Content Writer Agent · UC-01</h1>
      <p className="muted">Phân tích brief thương hiệu và sinh tập prompt người dùng hay hỏi AI.</p>

      <form onSubmit={submit}>
        <label htmlFor="brief">Brief thương hiệu</label>
        <textarea
          id="brief"
          required
          maxLength={20000}
          rows={12}
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="Dán brief dạng văn bản tự do: giới thiệu, sản phẩm, khách hàng, giọng văn..."
        />
        <fieldset>
          <legend>Chủ đề (1-3)</legend>
          {topics.map((topic, i) => (
            <input
              key={i}
              aria-label={`Chủ đề ${i + 1}`}
              required={i === 0}
              value={topic}
              onChange={(e) => setTopics(topics.map((t, j) => (j === i ? e.target.value : t)))}
              placeholder={i === 0 ? 'Ví dụ: sơn chống nóng mái tôn' : 'Không bắt buộc'}
            />
          ))}
        </fieldset>
        <button type="submit" disabled={status === 'running'}>Chạy UC-01</button>
      </form>

      {(error || notice) && (
        <div className="box error" role="alert">
          <h3>{error ? ERROR_TITLES[error.reason as string] ?? 'Lỗi không mong đợi' : notice}</h3>
          {error && <p>{error.message as string}</p>}
          {runId && <p>Mã run để tra trace: <code>{runId}</code></p>}
        </div>
      )}

      {events.length > 0 && (
        <section>
          <h2>Các bước của agent</h2>
          <ol className="timeline" aria-live="polite">
            {events.map((e, i) => (
              <li key={i}>
                <time>{new Date(e.ts).toLocaleTimeString('vi-VN')}</time> {describeEvent(e)}
              </li>
            ))}
            {status === 'running' && <li className="muted">Agent đang chạy…</li>}
          </ol>
        </section>
      )}

      {output && (
        <>
          <ProfileView profile={output.brand_profile as BrandProfile} />
          <PromptTable promptSet={output.prompt_set as PromptSet} />
        </>
      )}
    </main>
  )
}
