import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  fetchRuns,
  loadPromptSet,
  resumeRun,
  startRun,
  startRunUC02,
  startRunUC03,
  startRunUC04,
  startRunUC09,
  submitApproval,
  watchRun,
} from './api'
import type {
  ApprovalDecision,
  Article,
  BrandProfile,
  ClaimReport,
  PromptSet,
  ResearchReport,
  RunSummary,
  TraceEvent,
} from './api'
import { ArticleView } from './ArticleView'
import { CalendarView } from './CalendarView'
import { FactCheckPanel } from './FactCheckPanel'
import { ProfileView, PromptTable, ResearchReportView } from './Results'

type Status = 'idle' | 'running' | 'awaiting_approval' | 'done' | 'failed'
type Tab = 'uc01' | 'uc02' | 'uc03' | 'uc04' | 'uc09' | 'history'

const MAX_UC03_PROMPTS = 8

const ERROR_TITLES: Record<string, string> = {
  InputError: 'Đầu vào chưa hợp lệ',
  ConfigError: 'Server thiếu cấu hình',
  llm_error: 'Không gọi được Gemini',
  max_iterations: 'Agent dừng giữa chừng',
  loop_detected: 'Agent dừng giữa chừng',
  repair_failed: 'Agent dừng giữa chừng',
}

/** Một dòng tiếng Việt cho mỗi trace event (agent/loop.py, uc01..04, uc09, graph.py ghi). */
function describeEvent(e: TraceEvent): string {
  const d = e as Record<string, any>
  switch (e.event) {
    case 'input':
      if (d.brief) return `Nhận brief (${d.brief.length} ký tự), chủ đề: ${d.topics?.join(', ')}`
      if (d.revise) return `Nhận ${d.feedback?.length ?? 0} dòng phản hồi để sửa bài`
      if (d.prompts) return `Nhận chủ đề: ${d.topic}, ${d.prompts.length} prompt mục tiêu`
      if (d.topic) return `Nhận chủ đề: ${d.topic}, ${d.questions?.length ?? 0} câu hỏi`
      return 'Bắt đầu tác vụ'
    case 'node':
      return `Node ${d.name}${d.item_id ? ` [${d.item_id}]` : ''}: ${d.status}${d.message ? ' — ' + d.message : ''}`
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
      if (d.action === 'outline_ready') return `Dàn ý đạt: ${d.h2?.length ?? 0} mục`
      if (d.action === 'check_similarity') {
        return `Kiểm trùng 8-gram: ${(d.max_ratio * 100).toFixed(1)}%${d.url ? ' với ' + d.url : ''}`
      }
      if (d.action === 'calendar_planned') {
        return `📅 Đã lập lịch nội dung: ${d.total_items} bài trên các tuần ${d.weeks?.join(', ')}`
      }
      if (d.action === 'await_approval') {
        return `🛑 Chờ người duyệt bài [${d.item_id}] "${d.title}" (${d.blocking ?? 0} claim chặn)`
      }
      if (d.action === 'approval') {
        return `👤 Người duyệt (${d.reviewer}) quyết định ${d.decision} bài [${d.item_id}]: ${d.reason}`
      }
      if (d.action === 'compact') {
        return `🗜️ Nén ngữ cảnh (compaction) khi đạt ${d.tokens_before} token`
      }
      return `Quyết định: ${d.action}`
    case 'error':
      return `Lỗi (${d.reason}): ${d.message}`
    case 'output':
      if (d.calendar) return `Xong lịch nội dung UC-09 (${d.calendar.items?.length ?? 0} bài)`
      if (d.prompt_set) return `Xong: ${d.prompt_set.prompts.length} prompt`
      if (d.report && d.report.answers) return `Xong: ${d.report.answers.length} câu trả lời nghiên cứu`
      if (d.report && d.report.claims) return `Xong: fact-check ${d.report.claims.length} khẳng định`
      if (d.article) return `Xong: bài viết ${d.article.citations?.length ?? 0} trích dẫn`
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

  // UC-03 state: PromptSet lấy từ run UC-01 vừa chạy hoặc từ mã run nhập tay
  const [promptSet, setPromptSet] = useState<PromptSet | null>(null)
  const [promptSource, setPromptSource] = useState<string | null>(null)
  const [uc01RunId, setUc01RunId] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [topicUC03, setTopicUC03] = useState('')
  const [loadNotice, setLoadNotice] = useState<string | null>(null)

  // UC-04 state: nội dung bài Markdown nhập tay hoặc từ UC-03
  const [articleMarkdown, setArticleMarkdown] = useState('')
  const [articleTitle, setArticleTitle] = useState('Bài viết kiểm chứng')

  // UC-09 state
  const [briefUC09, setBriefUC09] = useState(
    'Skyveil là thương hiệu sơn và vật liệu chống nóng mái nhà tại TP.HCM, Đồng Nai, Tây Ninh. Dòng sản phẩm chính: Skyveil R200, D500, P100.',
  )
  const [topicsUC09, setTopicsUC09] = useState(['sơn chống nóng mái tôn', '', ''])

  // History state
  const [runsHistory, setRunsHistory] = useState<RunSummary[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

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

  function attachStream(id: string, resetEvents = false) {
    closeRun.current?.()
    if (resetEvents) setEvents([])
    setRunId(id)
    setNotice(null)
    setStatus('running')
    let seenNode = false
    closeRun.current = watchRun(
      id,
      (event) => {
        if (event.event === 'node' || event.uc === 'uc09') seenNode = true
        setEvents((prev) => [...prev, event])
        if (event.event === 'decision' && event.action === 'await_approval') {
          setStatus('awaiting_approval')
          setTab('uc09')
        }
        if (event.event === 'output') {
          if (!seenNode || event.uc === 'uc09' || 'calendar' in event) {
            setStatus('done')
          }
          if (event.prompt_set) applyPromptSet(event.prompt_set as PromptSet, id)
        }
        if (event.event === 'error') setStatus('failed')
      },
      () => {
        setNotice(`Mất kết nối tới run ${id}.`)
        setStatus('failed')
      },
    )
  }

  async function refreshHistory() {
    setLoadingHistory(true)
    try {
      setRunsHistory(await fetchRuns())
    } catch (err) {
      setNotice((err as Error).message)
    } finally {
      setLoadingHistory(false)
    }
  }

  useEffect(() => {
    if (tab === 'history') {
      void refreshHistory()
    }
  }, [tab])

  async function submitUC01(e: FormEvent) {
    e.preventDefault()
    resetState()
    try {
      const id = await startRun(brief, topics.filter((t) => t.trim()))
      attachStream(id, true)
    } catch (err) {
      setNotice((err as Error).message)
      setStatus('failed')
    }
  }

  function applyPromptSet(set: PromptSet, sourceRunId: string) {
    setPromptSet(set)
    setPromptSource(sourceRunId)
    setPicked(set.prompts.slice(0, 5).map((p) => p.id))
    setTopicUC03((old) => old || set.prompts[0]?.topic || '')
  }

  async function loadUC01Run() {
    setLoadNotice(null)
    try {
      applyPromptSet(await loadPromptSet(uc01RunId.trim()), uc01RunId.trim())
    } catch (err) {
      setLoadNotice((err as Error).message)
    }
  }

  function togglePrompt(id: string) {
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  async function submitUC03(e: FormEvent) {
    e.preventDefault()
    if (!promptSet) return
    resetState()
    try {
      const prompts = promptSet.prompts.filter((p) => picked.includes(p.id))
      const id = await startRunUC03(topicUC03, prompts)
      attachStream(id, true)
    } catch (err) {
      setNotice((err as Error).message)
      setStatus('failed')
    }
  }

  async function submitUC04(e: FormEvent) {
    e.preventDefault()
    resetState()
    try {
      const dummyArticle: Article = {
        outline: {
          title: articleTitle,
          meta_description: '',
          primary_keyword: '',
          secondary_keywords: [],
          target_prompts: [],
          sections: [],
          faq: [],
        },
        markdown: articleMarkdown,
        citations: [],
        notes: [],
      }
      const id = await startRunUC04(dummyArticle)
      attachStream(id, true)
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
      attachStream(id, true)
    } catch (err) {
      setNotice((err as Error).message)
      setStatus('failed')
    }
  }

  async function submitUC09(e: FormEvent) {
    e.preventDefault()
    resetState()
    try {
      const validTopics = topicsUC09.filter((t) => t.trim())
      const id = await startRunUC09(briefUC09, validTopics, false)
      attachStream(id, true)
    } catch (err) {
      setNotice((err as Error).message)
      setStatus('failed')
    }
  }

  async function handleApproveUC09(decision: ApprovalDecision) {
    if (!runId) return
    await submitApproval(runId, decision)
    attachStream(runId, true)
  }

  async function handleResumeUC09(targetId?: string) {
    const id = targetId ?? runId
    if (!id) return
    await resumeRun(id)
    setTab('uc09')
    attachStream(id, true)
  }

  function inspectHistoricalRun(item: RunSummary) {
    const validTab: Tab =
      item.uc === 'uc02' || item.uc === 'uc03' || item.uc === 'uc04' || item.uc === 'uc09'
        ? item.uc
        : 'uc01'
    setTab(validTab)
    attachStream(item.run_id, true)
  }

  const output = [...events].reverse().find((e) => e.event === 'output')
  const error = [...events].reverse().find((e) => e.event === 'error')

  return (
    <main>
      <header
        style={{
          marginBottom: '1.5rem',
          display: 'flex',
          gap: '0.5rem',
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <button
          type="button"
          onClick={() => { setTab('uc01'); setEvents([]); setStatus('idle'); setNotice(null) }}
          style={{ fontWeight: tab === 'uc01' ? 'bold' : 'normal' }}
        >
          UC-01: Brief & Prompt
        </button>
        <button
          type="button"
          onClick={() => { setTab('uc02'); setEvents([]); setStatus('idle'); setNotice(null) }}
          style={{ fontWeight: tab === 'uc02' ? 'bold' : 'normal' }}
        >
          UC-02: Nghiên cứu & KB
        </button>
        <button
          type="button"
          onClick={() => { setTab('uc03'); setEvents([]); setStatus('idle'); setNotice(null) }}
          style={{ fontWeight: tab === 'uc03' ? 'bold' : 'normal' }}
        >
          UC-03: Dàn ý & Viết bài
        </button>
        <button
          type="button"
          onClick={() => { setTab('uc04'); setEvents([]); setStatus('idle'); setNotice(null) }}
          style={{ fontWeight: tab === 'uc04' ? 'bold' : 'normal' }}
        >
          UC-04: Fact-checker
        </button>
        <button
          type="button"
          onClick={() => { setTab('uc09'); setNotice(null) }}
          style={{ fontWeight: tab === 'uc09' ? 'bold' : 'normal' }}
        >
          UC-09: Lịch 8 bài & Duyệt
        </button>
        <button
          type="button"
          onClick={() => { setTab('history'); setNotice(null) }}
          style={{ fontWeight: tab === 'history' ? 'bold' : 'normal', background: '#374151' }}
        >
          🗂️ Lịch sử Run
        </button>
      </header>

      {tab === 'history' && (
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h1>Lịch sử các lần chạy (Runs)</h1>
            <button type="button" onClick={refreshHistory} disabled={loadingHistory}>
              Làm mới
            </button>
          </div>
          <p className="muted">
            Lưu trữ bền vững trong bảng <code>runs</code> (Postgres) và thư mục <code>traces/</code>, giữ nguyên sau khi server khởi động lại.
          </p>

          {runsHistory.length === 0 ? (
            <p className="muted">{loadingHistory ? 'Đang tải…' : 'Chưa có run nào được ghi nhận.'}</p>
          ) : (
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Mã Run (run_id)</th>
                    <th>Use Case</th>
                    <th>Trạng thái</th>
                    <th>Thời gian tạo</th>
                    <th>Hành động</th>
                  </tr>
                </thead>
                <tbody>
                  {runsHistory.map((item) => (
                    <tr key={item.run_id}>
                      <td><code>{item.run_id}</code></td>
                      <td><span className="badge">{item.uc.toUpperCase()}</span></td>
                      <td>
                        <strong>{item.status}</strong>
                      </td>
                      <td>
                        {item.created_at ? new Date(item.created_at).toLocaleString('vi-VN') : '—'}
                      </td>
                      <td style={{ display: 'flex', gap: '8px' }}>
                        <button
                          type="button"
                          className="link"
                          onClick={() => inspectHistoricalRun(item)}
                        >
                          {item.status === 'awaiting_approval' ? '🛑 Mở màn hình duyệt' : 'Xem lại'}
                        </button>
                        {item.uc === 'uc09' && item.status !== 'done' && (
                          <button
                            type="button"
                            className="link"
                            onClick={() => void handleResumeUC09(item.run_id)}
                          >
                            ▶️ Resume
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === 'uc09' && (
        <>
          <h1>GEO Content Writer Agent · UC-09</h1>
          <p className="muted">
            Workflow LangGraph: phân tích brief (UC-01) → lập lịch nội dung 4 tuần (≥ 8 bài, chống trùng từ khoá) → nghiên cứu (UC-02) → viết bài (UC-03) → fact-check (UC-04) → cổng người duyệt.
          </p>

          <form onSubmit={submitUC09}>
            <label htmlFor="brief-uc09">Brief thương hiệu</label>
            <textarea
              id="brief-uc09"
              required
              maxLength={20000}
              rows={5}
              value={briefUC09}
              onChange={(e) => setBriefUC09(e.target.value)}
              placeholder="Nhập brief thương hiệu để lập lịch 8 bài..."
            />
            <fieldset>
              <legend>Chủ đề chiến dịch (1-3)</legend>
              {topicsUC09.map((topic, i) => (
                <input
                  key={i}
                  aria-label={`Chủ đề UC-09 ${i + 1}`}
                  required={i === 0}
                  value={topic}
                  onChange={(e) =>
                    setTopicsUC09(topicsUC09.map((t, j) => (j === i ? e.target.value : t)))
                  }
                  placeholder={i === 0 ? 'Ví dụ: sơn chống nóng mái tôn' : 'Không bắt buộc'}
                />
              ))}
            </fieldset>
            <button type="submit" disabled={status === 'running'}>
              Khởi chạy lịch nội dung UC-09
            </button>
          </form>

          {runId && events.length > 0 && (
            <CalendarView
              runId={runId}
              events={events}
              canResume={status !== 'running' && status !== 'done'}
              onApprove={handleApproveUC09}
              onResume={() => handleResumeUC09(runId)}
            />
          )}
        </>
      )}

      {tab === 'uc03' && (
        <>
          <h1>GEO Content Writer Agent · UC-03</h1>
          <p className="muted">
            Lập dàn ý GEO và viết bài theo giọng thương hiệu; mọi số liệu có trích dẫn tới kho tri thức.
          </p>

          <fieldset>
            <legend>PromptSet từ một run UC-01</legend>
            {promptSource && promptSet ? (
              <p>Đang dùng PromptSet của run <code>{promptSource}</code> ({promptSet.prompts.length} prompt).</p>
            ) : (
              <p className="muted">Chạy UC-01 ở tab đầu, hoặc nhập mã run UC-01 đã xong.</p>
            )}
            <div className="prompt-pick">
              <input
                id="uc01-run-id"
                aria-label="Mã run UC-01"
                value={uc01RunId}
                onChange={(e) => setUc01RunId(e.target.value)}
                placeholder="Mã run UC-01 (32 ký tự)"
                pattern="[0-9a-f]{32}"
              />
              <button type="button" onClick={loadUC01Run} disabled={!/^[0-9a-f]{32}$/.test(uc01RunId.trim())}>
                Tải PromptSet
              </button>
            </div>
            {loadNotice && <p role="alert">{loadNotice}</p>}
          </fieldset>

          {promptSet && (
            <form onSubmit={submitUC03}>
              <label htmlFor="topic-uc03">Chủ đề bài viết</label>
              <input id="topic-uc03" required value={topicUC03} onChange={(e) => setTopicUC03(e.target.value)} />
              <fieldset>
                <legend>
                  Prompt mục tiêu của bài ({picked.length}/{MAX_UC03_PROMPTS} đã chọn)
                </legend>
                <div className="scroll" style={{ maxHeight: 320 }}>
                  <table>
                    <tbody>
                      {promptSet.prompts.map((p) => (
                        <tr key={p.id}>
                          <td>
                            <input
                              type="checkbox"
                              id={`pick-${p.id}`}
                              checked={picked.includes(p.id)}
                              disabled={!picked.includes(p.id) && picked.length >= MAX_UC03_PROMPTS}
                              onChange={() => togglePrompt(p.id)}
                            />
                          </td>
                          <td><label htmlFor={`pick-${p.id}`}>{p.text}</label></td>
                          <td>{p.intent}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </fieldset>
              <button type="submit" disabled={status === 'running' || picked.length === 0}>
                Viết bài UC-03
              </button>
            </form>
          )}
        </>
      )}

      {tab === 'uc01' && (
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
      )}

      {tab === 'uc02' && (
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

      {tab === 'uc04' && (
        <>
          <h1>GEO Content Writer Agent · UC-04</h1>
          <p className="muted">
            Kiểm chứng sự thật (Fact-checker): bóc tách từng khẳng định nguyên tử, tra cứu kho tri thức và web, áp dụng luật bằng chứng để phán quyết.
          </p>
          <form onSubmit={submitUC04}>
            <label htmlFor="uc04-title">Tiêu đề bài viết</label>
            <input
              id="uc04-title"
              required
              value={articleTitle}
              onChange={(e) => setArticleTitle(e.target.value)}
              placeholder="Tiêu đề bài viết cần fact-check"
            />

            <label htmlFor="uc04-markdown">Nội dung bài viết (Markdown)</label>
            <textarea
              id="uc04-markdown"
              rows={10}
              required
              value={articleMarkdown}
              onChange={(e) => setArticleMarkdown(e.target.value)}
              placeholder="Dán nội dung bài Markdown vào đây để Fact-checker kiểm tra..."
            />
            <button type="submit" disabled={status === 'running'}>Chạy Fact-checker (UC-04)</button>
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

      {events.length > 0 && tab !== 'history' && (
        <section style={{ marginTop: '1.5rem' }}>
          <h2>Tiến trình của agent</h2>
          <ol className="timeline" aria-live="polite">
            {events.map((e, i) => (
              <li key={i}>
                <time>{new Date(e.ts).toLocaleTimeString('vi-VN')}</time> {describeEvent(e)}
              </li>
            ))}
            {status === 'running' && <li className="muted">Agent đang chạy…</li>}
            {status === 'awaiting_approval' && (
              <li style={{ color: '#c2410c', fontWeight: 600 }}>
                Đang tạm dừng chờ người duyệt (Approval Gate)…
              </li>
            )}
          </ol>
        </section>
      )}

      {output && tab === 'uc01' && Boolean(output.prompt_set) && (
        <>
          <ProfileView profile={output.brand_profile as BrandProfile} />
          <PromptTable promptSet={output.prompt_set as PromptSet} />
        </>
      )}

      {output && tab === 'uc03' && Boolean(output.article) && (
        <ArticleView article={output.article as Article} />
      )}

      {output && tab === 'uc02' && Boolean(output.report) && (
        <ResearchReportView report={output.report as ResearchReport} events={events} />
      )}

      {output && tab === 'uc04' && Boolean(output.report) && (
        <FactCheckPanel report={output.report as ClaimReport} />
      )}
    </main>
  )
}
