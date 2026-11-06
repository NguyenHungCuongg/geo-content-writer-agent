import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { startRun, startRunUC02, watchRun } from './api'
import type { BrandProfile, PromptSet, ResearchReport, TraceEvent } from './api'
import { ProfileView, PromptTable, ResearchReportView } from './Results'

type Status = 'idle' | 'running' | 'done' | 'failed'
type Tab = 'uc01' | 'uc02'

const ERROR_TITLES: Record<string, string> = {
  InputError: 'Đầu vào chưa hợp lệ',
  ConfigError: 'Server thiếu cấu hình',
  llm_error: 'Không gọi được Gemini',
  max_iterations: 'Agent dừng giữa chừng',
  loop_detected: 'Agent dừng giữa chừng',
  repair_failed: 'Agent dừng giữa chừng',
}

/** Một dòng tiếng Việt cho mỗi trace event (event do agent/loop.py, agent/uc01.py, agent/uc02.py ghi). */
function describeEvent(e: TraceEvent): string {
  const d = e as Record<string, any>
  switch (e.event) {
    case 'input':
      if (d.brief) return `Nhận brief (${d.brief.length} ký tự), chủ đề: ${d.topics?.join(', ')}`
      if (d.topic) return `Nhận chủ đề: ${d.topic}, ${d.questions?.length ?? 0} câu hỏi`
      return 'Bắt đầu tác vụ'
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
      if (d.action === 'flag_suspicious') return `⚠️ Cảnh báo: Phát hiện câu chỉ dẫn AI trên ${d.url}`
      if (d.action === 'block_url') return `⛔ Chặn URL ngoài allowlist: ${d.url}`
      return `Quyết định: ${d.action}`
    case 'error':
      return `Lỗi (${d.reason}): ${d.message}`
    case 'output':
      if (d.prompt_set) return `Xong: ${d.prompt_set.prompts.length} prompt`
      if (d.report) return `Xong: ${d.report.answers?.length ?? 0} câu trả lời nghiên cứu`
      return 'Hoàn thành'
    default:
      return e.event
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('uc01')

  // UC-01 state
  const [brief, setBrief] = useState('')
  const [topics, setTopics] = useState(['', '', ''])

  // UC-02 state
  const [topicUC02, setTopicUC02] = useState('sơn chống nóng mái tôn')
  const [questions, setQuestions] = useState([
    'Tuân thủ QCVN 09:2017/BXD có thể tiết kiệm bao nhiêu phần trăm năng lượng?',
    'Nhiệt độ mặt mái tôn mùa hè có thể lên tới bao nhiêu độ C?',
  ])

  // Shared state
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [notice, setNotice] = useState<string | null>(null)
  const closeRun = useRef<(() => void) | null>(null)

  function resetState() {
    closeRun.current?.()
    setEvents([])
    setRunId(null)
    setNotice(null)
    setStatus('running')
  }

  async function submitUC01(e: FormEvent) {
    e.preventDefault()
    resetState()
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

  async function submitUC02(e: FormEvent) {
    e.preventDefault()
    resetState()
    try {
      const validQuestions = questions.filter((q) => q.trim())
      const id = await startRunUC02(topicUC02, validQuestions)
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
      <header style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
        <button
          type="button"
          onClick={() => { setTab('uc01'); setEvents([]); setStatus('idle'); }}
          style={{ fontWeight: tab === 'uc01' ? 'bold' : 'normal' }}
        >
          UC-01: Phân tích brief & prompt
        </button>
        <button
          type="button"
          onClick={() => { setTab('uc02'); setEvents([]); setStatus('idle'); }}
          style={{ fontWeight: tab === 'uc02' ? 'bold' : 'normal' }}
        >
          UC-02: Nghiên cứu & kho tri thức
        </button>
      </header>

      {tab === 'uc01' ? (
        <>
          <h1>GEO Content Writer Agent · UC-01</h1>
          <p className="muted">Phân tích brief thương hiệu và sinh tập prompt người dùng hay hỏi AI.</p>

          <form onSubmit={submitUC01}>
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
        </>
      ) : (
        <>
          <h1>GEO Content Writer Agent · UC-02</h1>
          <p className="muted">Nghiên cứu nguồn tin cậy trong allowlist, dựng kho tri thức RAG và trả lời có trích dẫn.</p>

          <form onSubmit={submitUC02}>
            <label htmlFor="topic-uc02">Chủ đề nghiên cứu</label>
            <input
              id="topic-uc02"
              required
              value={topicUC02}
              onChange={(e) => setTopicUC02(e.target.value)}
              placeholder="Ví dụ: sơn chống nóng mái tôn"
            />
            <fieldset>
              <legend>Danh sách câu hỏi nghiên cứu</legend>
              {questions.map((q, i) => (
                <input
                  key={i}
                  aria-label={`Câu hỏi ${i + 1}`}
                  required={i === 0}
                  value={q}
                  onChange={(e) => setQuestions(questions.map((item, j) => (j === i ? e.target.value : item)))}
                  placeholder={`Câu hỏi ${i + 1}`}
                />
              ))}
              <button
                type="button"
                onClick={() => setQuestions([...questions, ''])}
                style={{ marginTop: '0.5rem' }}
              >
                + Thêm câu hỏi
              </button>
            </fieldset>
            <button type="submit" disabled={status === 'running'}>Chạy UC-02</button>
          </form>
        </>
      )}

      {(error || notice) && (
        <div className="box error" role="alert" style={{ marginTop: '1.5rem' }}>
          <h3>{error ? ERROR_TITLES[error.reason as string] ?? 'Lỗi không mong đợi' : notice}</h3>
          {error && <p>{error.message as string}</p>}
          {runId && <p>Mã run để tra trace: <code>{runId}</code></p>}
        </div>
      )}

      {events.length > 0 && (
        <section style={{ marginTop: '1.5rem' }}>
          <h2>Tiến trình của agent</h2>
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

      {output && tab === 'uc01' && Boolean(output.prompt_set) && (
        <>
          <ProfileView profile={output.brand_profile as BrandProfile} />
          <PromptTable promptSet={output.prompt_set as PromptSet} />
        </>
      )}

      {output && tab === 'uc02' && Boolean(output.report) && (
        <ResearchReportView report={output.report as ResearchReport} events={events} />
      )}
    </main>
  )
}
