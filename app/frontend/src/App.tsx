import { useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
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
import {
  AlertIcon,
  BanIcon,
  BrandMark,
  CalendarIcon,
  CheckIcon,
  CompressIcon,
  HistoryIcon,
  LockIcon,
  PlayIcon,
  PlusIcon,
  RefreshIcon,
  UserIcon,
} from './Icons'
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

const STATUS_LABELS: Record<Status, string> = {
  idle: 'Sẵn sàng',
  running: 'Đang chạy',
  awaiting_approval: 'Chờ duyệt',
  done: 'Hoàn tất',
  failed: 'Lỗi',
}

const TAB_HEADINGS: Record<Tab, { title: string; lead: string }> = {
  uc01: {
    title: 'Phân tích brief và sinh tập prompt',
    lead: 'Trích xuất hồ sơ thương hiệu Skyveil và tạo danh sách câu hỏi người dùng thường hỏi AI.',
  },
  uc02: {
    title: 'Nghiên cứu nguồn tin và kho tri thức',
    lead: 'Thu thập tài liệu trong allowlist, nạp kho tri thức RAG và tổng hợp câu trả lời có trích dẫn.',
  },
  uc03: {
    title: 'Lập dàn ý GEO và viết bài',
    lead: 'Xây dựng cấu trúc bài viết theo giọng thương hiệu; mọi số liệu đều gắn nguồn trong kho tri thức.',
  },
  uc04: {
    title: 'Kiểm chứng sự thật (Fact-checker)',
    lead: 'Tách từng khẳng định nguyên tử, đối chiếu kho tri thức và áp dụng luật bằng chứng để phán quyết.',
  },
  uc09: {
    title: 'Lịch nội dung 4 tuần và cổng duyệt',
    lead: 'Điều phối LangGraph từ brief đến lịch 8 bài, nghiên cứu, viết bài, fact-check và phê duyệt thủ công.',
  },
  history: {
    title: 'Lịch sử các lần chạy',
    lead: 'Dữ liệu lưu bền vững trong bảng runs (Postgres) và thư mục traces, xem lại hoặc chạy tiếp sau khởi động lại.',
  },
}

type EventDisplay = {
  text: string
  tone: 'neutral' | 'info' | 'warning' | 'error' | 'success'
  icon: ReactNode
}

/** Một dòng tiếng Việt và mức độ trạng thái cho mỗi trace event (agent/loop.py, uc01..04, uc09, graph.py). */
function describeEvent(e: TraceEvent): EventDisplay {
  const d = e as Record<string, any>
  switch (e.event) {
    case 'input':
      if (d.brief) {
        return {
          text: `Nhận brief (${d.brief.length} ký tự), chủ đề: ${d.topics?.join(', ')}`,
          tone: 'info',
          icon: <PlayIcon />,
        }
      }
      if (d.revise) {
        return {
          text: `Nhận ${d.feedback?.length ?? 0} dòng phản hồi để sửa bài`,
          tone: 'info',
          icon: <RefreshIcon />,
        }
      }
      if (d.prompts) {
        return {
          text: `Nhận chủ đề: ${d.topic}, ${d.prompts.length} prompt mục tiêu`,
          tone: 'info',
          icon: <PlayIcon />,
        }
      }
      if (d.topic) {
        return {
          text: `Nhận chủ đề: ${d.topic}, ${d.questions?.length ?? 0} câu hỏi`,
          tone: 'info',
          icon: <PlayIcon />,
        }
      }
      return { text: 'Bắt đầu tác vụ', tone: 'info', icon: <PlayIcon /> }
    case 'node':
      return {
        text: `Node ${d.name}${d.item_id ? ` [${d.item_id}]` : ''}: ${d.status}${d.message ? `: ${d.message}` : ''}`,
        tone: d.status === 'error' ? 'error' : d.status === 'done' ? 'success' : 'info',
        icon: d.status === 'error' ? <AlertIcon /> : d.status === 'done' ? <CheckIcon /> : <PlayIcon />,
      }
    case 'llm_call':
      return {
        text:
          `Gọi ${d.model}${d.structured ? ' (chốt kết quả JSON)' : ''}: ` +
          `${d.input_tokens} token vào, ${d.output_tokens} token ra`,
        tone: 'neutral',
        icon: <PlayIcon />,
      }
    case 'tool_call':
      return {
        text: `Tool ${d.name}: ${d.ok ? 'xong' : 'lỗi: ' + d.error} (${d.duration_ms} ms)`,
        tone: d.ok ? 'neutral' : 'error',
        icon: d.ok ? <CheckIcon /> : <AlertIcon />,
      }
    case 'skill_invocation':
      return { text: `Dùng skill ${d.name}`, tone: 'info', icon: <CheckIcon /> }
    case 'decision':
      if (d.action === 'repair') {
        return {
          text: `Output sai schema, yêu cầu sửa lần ${d.attempt}: ${d.error}`,
          tone: 'warning',
          icon: <AlertIcon />,
        }
      }
      if (d.action === 'skip_skill') {
        return { text: `Bỏ qua skill: ${d.reason}`, tone: 'neutral', icon: <AlertIcon /> }
      }
      if (d.action === 'flag_suspicious') {
        return {
          text: `Cảnh báo: Phát hiện câu chỉ dẫn AI trên ${d.url}`,
          tone: 'warning',
          icon: <AlertIcon />,
        }
      }
      if (d.action === 'block_url') {
        return { text: `Chặn URL ngoài allowlist: ${d.url}`, tone: 'error', icon: <BanIcon /> }
      }
      if (d.action === 'outline_ready') {
        return { text: `Dàn ý đạt: ${d.h2?.length ?? 0} mục`, tone: 'success', icon: <CheckIcon /> }
      }
      if (d.action === 'check_similarity') {
        return {
          text: `Kiểm trùng 8-gram: ${(d.max_ratio * 100).toFixed(1)}%${d.url ? ' với ' + d.url : ''}`,
          tone: 'info',
          icon: <CheckIcon />,
        }
      }
      if (d.action === 'calendar_planned') {
        return {
          text: `Đã lập lịch nội dung: ${d.total_items} bài trên các tuần ${d.weeks?.join(', ')}`,
          tone: 'success',
          icon: <CalendarIcon />,
        }
      }
      if (d.action === 'await_approval') {
        return {
          text: `Chờ người duyệt bài [${d.item_id}] "${d.title}" (${d.blocking ?? 0} claim chặn)`,
          tone: 'warning',
          icon: <LockIcon />,
        }
      }
      if (d.action === 'approval') {
        return {
          text: `Người duyệt (${d.reviewer}) quyết định ${d.decision} bài [${d.item_id}]: ${d.reason}`,
          tone: d.decision === 'approve' ? 'success' : 'warning',
          icon: <UserIcon />,
        }
      }
      if (d.action === 'compact') {
        return {
          text: `Nén ngữ cảnh (compaction) khi đạt ${d.tokens_before} token`,
          tone: 'info',
          icon: <CompressIcon />,
        }
      }
      return { text: `Quyết định: ${d.action}`, tone: 'neutral', icon: <CheckIcon /> }
    case 'error':
      return { text: `Lỗi (${d.reason}): ${d.message}`, tone: 'error', icon: <AlertIcon /> }
    case 'output':
      if (d.calendar) {
        return {
          text: `Xong lịch nội dung UC-09 (${d.calendar.items?.length ?? 0} bài)`,
          tone: 'success',
          icon: <CheckIcon />,
        }
      }
      if (d.prompt_set) {
        return {
          text: `Xong: ${d.prompt_set.prompts.length} prompt`,
          tone: 'success',
          icon: <CheckIcon />,
        }
      }
      if (d.report && d.report.answers) {
        return {
          text: `Xong: ${d.report.answers.length} câu trả lời nghiên cứu`,
          tone: 'success',
          icon: <CheckIcon />,
        }
      }
      if (d.report && d.report.claims) {
        return {
          text: `Xong: fact-check ${d.report.claims.length} khẳng định`,
          tone: 'success',
          icon: <CheckIcon />,
        }
      }
      if (d.article) {
        return {
          text: `Xong: bài viết ${d.article.citations?.length ?? 0} trích dẫn`,
          tone: 'success',
          icon: <CheckIcon />,
        }
      }
      return { text: 'Hoàn thành', tone: 'success', icon: <CheckIcon /> }
    default:
      return { text: e.event, tone: 'neutral', icon: <PlayIcon /> }
  }
}

export default function App() {
  const [tab, setTabState] = useState<Tab>('uc01')

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
  const [loadingPromptSet, setLoadingPromptSet] = useState(false)

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
  const [historyError, setHistoryError] = useState<string | null>(null)

  // Shared state
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [runUc, setRunUc] = useState<Tab | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [notice, setNotice] = useState<string | null>(null)
  const closeRun = useRef<(() => void) | null>(null)

  useEffect(() => () => closeRun.current?.(), [])

  function resetState() {
    closeRun.current?.()
    closeRun.current = null
    setEvents([])
    setRunId(null)
    setRunUc(null)
    setNotice(null)
    setStatus('running')
  }

  function attachStream(id: string, resetEvents = false, sourceUc?: Tab) {
    closeRun.current?.()
    closeRun.current = null
    if (resetEvents) setEvents([])
    setRunId(id)
    if (sourceUc) setRunUc(sourceUc)
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
          setTabState('uc09')
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
    setHistoryError(null)
    try {
      setRunsHistory(await fetchRuns())
    } catch (err) {
      setHistoryError((err as Error).message)
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
      attachStream(id, true, 'uc01')
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
    const normalizedId = uc01RunId.trim().toLowerCase()
    setLoadNotice(null)
    setLoadingPromptSet(true)
    try {
      applyPromptSet(await loadPromptSet(normalizedId), normalizedId)
    } catch (err) {
      setLoadNotice((err as Error).message)
    } finally {
      setLoadingPromptSet(false)
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
      attachStream(id, true, 'uc03')
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
      attachStream(id, true, 'uc04')
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
      attachStream(id, true, 'uc02')
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
      attachStream(id, true, 'uc09')
    } catch (err) {
      setNotice((err as Error).message)
      setStatus('failed')
    }
  }

  async function handleApproveUC09(decision: ApprovalDecision) {
    if (!runId) return
    await submitApproval(runId, decision)
    attachStream(runId, true, 'uc09')
  }

  async function handleResumeUC09(targetId?: string) {
    const id = targetId ?? runId
    if (!id) return
    try {
      await resumeRun(id)
      setTabState('uc09')
      attachStream(id, true, 'uc09')
    } catch (err) {
      if (tab === 'history') {
        setNotice((err as Error).message)
        setStatus('failed')
        return
      }
      throw err
    }
  }

  function inspectHistoricalRun(item: RunSummary) {
    const validTab: Tab =
      item.uc === 'uc02' || item.uc === 'uc03' || item.uc === 'uc04' || item.uc === 'uc09'
        ? item.uc
        : 'uc01'
    setTabState(validTab)
    attachStream(item.run_id, true, validTab)
  }

  function setTab(next: Tab) {
    if (next !== 'history' && (next !== 'uc09' || (runUc && runUc !== 'uc09'))) {
      closeRun.current?.()
      closeRun.current = null
      setRunId(null)
      setRunUc(null)
      setEvents([])
      setStatus('idle')
    }
    setTabState(next)
  }

  const output = [...events].reverse().find((e) => e.event === 'output')
  const error = [...events].reverse().find((e) => e.event === 'error')
  const heading = TAB_HEADINGS[tab]

  return (
    <>
      <a className="skip" href="#main">Chuyển tới nội dung chính</a>

      <header className="app-header">
        <div className="container app-header__in">
          <div className="brand">
            <BrandMark />
            <span>Skyveil GEO</span>
          </div>

          <nav className="tab-nav" aria-label="Điều hướng tác vụ">
            <button
              type="button"
              className="tab-btn"
              aria-current={tab === 'uc01' ? 'page' : undefined}
              onClick={() => { setTab('uc01'); setEvents([]); setStatus('idle'); setNotice(null) }}
            >
              <span className="tab-btn__code">UC-01</span>
              <span>Brief & Prompt</span>
            </button>
            <button
              type="button"
              className="tab-btn"
              aria-current={tab === 'uc02' ? 'page' : undefined}
              onClick={() => { setTab('uc02'); setEvents([]); setStatus('idle'); setNotice(null) }}
            >
              <span className="tab-btn__code">UC-02</span>
              <span>Nghiên cứu & KB</span>
            </button>
            <button
              type="button"
              className="tab-btn"
              aria-current={tab === 'uc03' ? 'page' : undefined}
              onClick={() => { setTab('uc03'); setEvents([]); setStatus('idle'); setNotice(null) }}
            >
              <span className="tab-btn__code">UC-03</span>
              <span>Dàn ý & Viết bài</span>
            </button>
            <button
              type="button"
              className="tab-btn"
              aria-current={tab === 'uc04' ? 'page' : undefined}
              onClick={() => { setTab('uc04'); setEvents([]); setStatus('idle'); setNotice(null) }}
            >
              <span className="tab-btn__code">UC-04</span>
              <span>Fact-checker</span>
            </button>
            <button
              type="button"
              className="tab-btn"
              aria-current={tab === 'uc09' ? 'page' : undefined}
              onClick={() => { setTab('uc09'); setNotice(null) }}
            >
              <span className="tab-btn__code">UC-09</span>
              <span>Lịch 8 bài & Duyệt</span>
            </button>
            <button
              type="button"
              className="tab-btn"
              aria-current={tab === 'history' ? 'page' : undefined}
              onClick={() => { setTab('history'); setNotice(null) }}
            >
              <HistoryIcon />
              <span>Lịch sử Run</span>
            </button>
          </nav>

          <div className={`run-pill run-pill--${status}`} role="status" aria-live="polite">
            {status === 'running' && <span className="status-dot status-dot--running" aria-hidden="true" />}
            <span>{STATUS_LABELS[status]}</span>
            {runId && <code className="num">{runId.slice(0, 8)}</code>}
          </div>
        </div>
      </header>

      <main id="main" className="container app-main">
        <div className="page-head">
          <div className="page-head__copy">
            <h1>{heading.title}</h1>
            <p className="lead">{heading.lead}</p>
          </div>
          {tab === 'history' && (
            <button
              type="button"
              className="btn btn--quiet"
              onClick={refreshHistory}
              disabled={loadingHistory}
              aria-busy={loadingHistory}
            >
              <RefreshIcon />
              <span>{loadingHistory ? 'Đang tải…' : 'Làm mới'}</span>
            </button>
          )}
        </div>

        {tab === 'history' ? (
          <section className="section-block">
            {historyError && (
              <div className="alert alert--error" role="alert">
                <div className="alert__head">
                  <AlertIcon />
                  <h2>Không tải được danh sách run</h2>
                </div>
                <p>{historyError}</p>
              </div>
            )}
            {notice && (
              <div className="alert alert--error" role="alert">
                <div className="alert__head">
                  <AlertIcon />
                  <h2>Không thể chạy tiếp run</h2>
                </div>
                <p>{notice}</p>
              </div>
            )}

            {loadingHistory && runsHistory.length === 0 ? (
              <div className="skeleton-list" aria-busy="true" aria-label="Đang tải lịch sử run">
                <div className="skeleton-row" />
                <div className="skeleton-row" />
                <div className="skeleton-row" />
              </div>
            ) : runsHistory.length === 0 ? (
              <div className="empty-state">
                <p className="empty-state__title">Chưa có run nào được ghi nhận.</p>
                <p className="muted">Chạy một tác vụ ở UC-01 đến UC-09 để lưu vết vào Postgres và thư mục traces.</p>
              </div>
            ) : (
              <div className="scroll">
                <table className="responsive-table">
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
                        <td data-label="Mã Run"><code className="num">{item.run_id}</code></td>
                        <td data-label="Use Case"><span className="badge">{item.uc.toUpperCase()}</span></td>
                        <td data-label="Trạng thái">
                          <span
                            className={`status-pill status-pill--${
                              item.status === 'done' || item.status === 'approved'
                                ? 'approved'
                                : item.status === 'awaiting_approval'
                                  ? 'review'
                                  : item.status === 'failed'
                                    ? 'failed'
                                    : item.status === 'running'
                                      ? 'researching'
                                      : 'todo'
                            }`}
                          >
                            {item.status}
                          </span>
                        </td>
                        <td data-label="Thời gian tạo" className="num">
                          {item.created_at ? new Date(item.created_at).toLocaleString('vi-VN') : 'Chưa ghi nhận'}
                        </td>
                        <td data-label="Hành động">
                          <div className="row-actions">
                            <button
                              type="button"
                              className="link"
                              onClick={() => inspectHistoricalRun(item)}
                            >
                              {item.status === 'awaiting_approval' && <LockIcon />}
                              <span>{item.status === 'awaiting_approval' ? 'Mở màn hình duyệt' : 'Xem lại'}</span>
                            </button>
                            {item.uc === 'uc09' && item.status !== 'done' && (
                              <button
                                type="button"
                                className="link"
                                onClick={() => void handleResumeUC09(item.run_id)}
                              >
                                <PlayIcon />
                                <span>Resume</span>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : (
          <div className="workbench">
            <section className="panel panel--ticks ticks">
              {tab === 'uc01' && (
                <form className="uc-form" onSubmit={submitUC01}>
                  <div className="field-group">
                    <label className="field-label" htmlFor="brief">Brief thương hiệu</label>
                    <textarea
                      id="brief"
                      required
                      maxLength={20000}
                      rows={12}
                      value={brief}
                      onChange={(e) => setBrief(e.target.value)}
                      placeholder="Dán brief dạng văn bản tự do: giới thiệu, sản phẩm, khách hàng, giọng văn..."
                    />
                  </div>
                  <fieldset className="field-section">
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
                  <div className="form-actions">
                    <button
                      type="submit"
                      className="btn btn--primary"
                      disabled={status === 'running'}
                      aria-busy={status === 'running'}
                    >
                      <PlayIcon />
                      <span>{status === 'running' ? 'Đang chạy UC-01…' : 'Chạy UC-01'}</span>
                    </button>
                  </div>
                </form>
              )}

              {tab === 'uc02' && (
                <form className="uc-form" onSubmit={submitUC02}>
                  <div className="field-group">
                    <label className="field-label" htmlFor="topic-uc02">Chủ đề nghiên cứu</label>
                    <input
                      id="topic-uc02"
                      required
                      value={topicUC02}
                      onChange={(e) => setTopicUC02(e.target.value)}
                      placeholder="Ví dụ: sơn chống nóng mái tôn"
                    />
                  </div>
                  <fieldset className="field-section">
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
                    <div>
                      <button
                        type="button"
                        className="btn btn--quiet btn--compact"
                        onClick={() => setQuestions([...questions, ''])}
                      >
                        <PlusIcon />
                        <span>Thêm câu hỏi</span>
                      </button>
                    </div>
                  </fieldset>
                  <div className="form-actions">
                    <button
                      type="submit"
                      className="btn btn--primary"
                      disabled={status === 'running'}
                      aria-busy={status === 'running'}
                    >
                      <PlayIcon />
                      <span>{status === 'running' ? 'Đang chạy UC-02…' : 'Chạy UC-02'}</span>
                    </button>
                  </div>
                </form>
              )}

              {tab === 'uc03' && (
                <div className="uc-form">
                  <fieldset className="field-section">
                    <legend>PromptSet từ một run UC-01</legend>
                    {promptSource && promptSet ? (
                      <p>
                        Đang dùng PromptSet của run <code className="num">{promptSource}</code> ({promptSet.prompts.length} prompt).
                      </p>
                    ) : (
                      <p className="muted">Chạy UC-01 ở tab đầu, hoặc nhập mã run UC-01 đã xong.</p>
                    )}
                    <div className="field-row">
                      <input
                        id="uc01-run-id"
                        aria-label="Mã run UC-01"
                        value={uc01RunId}
                        onChange={(e) => setUc01RunId(e.target.value)}
                        placeholder="Mã run UC-01 (32 ký tự)"
                        pattern="[0-9a-fA-F]{32}"
                      />
                      <button
                        type="button"
                        className="btn btn--quiet"
                        onClick={loadUC01Run}
                        aria-busy={loadingPromptSet}
                        disabled={loadingPromptSet || !/^[0-9a-f]{32}$/.test(uc01RunId.trim().toLowerCase())}
                      >
                        {loadingPromptSet ? 'Đang tải…' : 'Tải PromptSet'}
                      </button>
                    </div>
                    <p className="field-hint">
                      {!promptSet && !/^[0-9a-f]{32}$/.test(uc01RunId.trim().toLowerCase())
                        ? 'Nhập mã run UC-01 gồm 32 ký tự hex để tải PromptSet.'
                        : ''}
                    </p>
                    {loadNotice && (
                      <p className="field-error" role="alert">{loadNotice}</p>
                    )}
                  </fieldset>

                  {promptSet && (
                    <form className="uc-form" onSubmit={submitUC03}>
                      <div className="field-group">
                        <label className="field-label" htmlFor="topic-uc03">Chủ đề bài viết</label>
                        <input
                          id="topic-uc03"
                          required
                          value={topicUC03}
                          onChange={(e) => setTopicUC03(e.target.value)}
                        />
                      </div>
                      <fieldset className="field-section">
                        <legend>
                          Prompt mục tiêu của bài (<span className="num">{picked.length}/{MAX_UC03_PROMPTS}</span> đã chọn)
                        </legend>
                        <div className="scroll table-scroll-cap">
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
                                  <td><span className="badge">{p.intent}</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </fieldset>
                      <div className="form-actions">
                        <button
                          type="submit"
                          className="btn btn--primary"
                          disabled={status === 'running' || picked.length === 0}
                          aria-busy={status === 'running'}
                        >
                          <PlayIcon />
                          <span>{status === 'running' ? 'Đang viết bài…' : 'Viết bài UC-03'}</span>
                        </button>
                      </div>
                      <p className="field-hint">
                        {picked.length === 0 ? 'Chọn ít nhất 1 prompt trong bảng trên để viết bài.' : ''}
                      </p>
                    </form>
                  )}
                </div>
              )}

              {tab === 'uc04' && (
                <form className="uc-form" onSubmit={submitUC04}>
                  <div className="field-group">
                    <label className="field-label" htmlFor="uc04-title">Tiêu đề bài viết</label>
                    <input
                      id="uc04-title"
                      required
                      value={articleTitle}
                      onChange={(e) => setArticleTitle(e.target.value)}
                      placeholder="Tiêu đề bài viết cần fact-check"
                    />
                  </div>
                  <div className="field-group">
                    <label className="field-label" htmlFor="uc04-markdown">Nội dung bài viết (Markdown)</label>
                    <textarea
                      id="uc04-markdown"
                      rows={10}
                      required
                      value={articleMarkdown}
                      onChange={(e) => setArticleMarkdown(e.target.value)}
                      placeholder="Dán nội dung bài Markdown vào đây để Fact-checker kiểm tra..."
                    />
                  </div>
                  <div className="form-actions">
                    <button
                      type="submit"
                      className="btn btn--primary"
                      disabled={status === 'running'}
                      aria-busy={status === 'running'}
                    >
                      <PlayIcon />
                      <span>{status === 'running' ? 'Đang kiểm chứng…' : 'Chạy Fact-checker (UC-04)'}</span>
                    </button>
                  </div>
                </form>
              )}

              {tab === 'uc09' && (
                <form className="uc-form" onSubmit={submitUC09}>
                  <div className="field-group">
                    <label className="field-label" htmlFor="brief-uc09">Brief thương hiệu</label>
                    <textarea
                      id="brief-uc09"
                      required
                      maxLength={20000}
                      rows={5}
                      value={briefUC09}
                      onChange={(e) => setBriefUC09(e.target.value)}
                      placeholder="Nhập brief thương hiệu để lập lịch 8 bài..."
                    />
                  </div>
                  <fieldset className="field-section">
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
                  <div className="form-actions">
                    <button
                      type="submit"
                      className="btn btn--primary"
                      disabled={status === 'running'}
                      aria-busy={status === 'running'}
                    >
                      <CalendarIcon />
                      <span>{status === 'running' ? 'Đang lập lịch…' : 'Khởi chạy lịch nội dung UC-09'}</span>
                    </button>
                  </div>
                </form>
              )}
            </section>

            <aside className="telemetry-rail">
              {(error || notice) && (
                <div className="alert alert--error" role="alert">
                  <div className="alert__head">
                    <AlertIcon />
                    <h2>{error ? ERROR_TITLES[error.reason as string] ?? 'Lỗi không mong đợi' : notice}</h2>
                  </div>
                  {error && <p>{error.message as string}</p>}
                  {runId && <p>Mã run để tra trace: <code className="num">{runId}</code></p>}
                </div>
              )}

              <section className="panel panel--ticks ticks">
                <div className="panel__head">
                  <h2>Tiến trình của agent</h2>
                  <span className="badge num">{events.length} sự kiện</span>
                </div>

                {events.length === 0 ? (
                  <div className="empty-state">
                    <p className="empty-state__title">Chưa có phiên chạy nào đang phát</p>
                    <p className="muted">
                      Khi gửi biểu mẫu bên trái, từng bước gọi Gemini, tool và quyết định của harness sẽ stream trực tiếp tại đây.
                    </p>
                  </div>
                ) : (
                  <ol className="timeline" aria-live="polite">
                    {events.map((e, i) => {
                      const info = describeEvent(e)
                      return (
                        <li key={i} className={`timeline__item timeline__item--${info.tone}`}>
                          <time className="timeline__time num">
                            {new Date(e.ts).toLocaleTimeString('vi-VN')}
                          </time>
                          <span className="timeline__icon">{info.icon}</span>
                          <span className="timeline__text">{info.text}</span>
                        </li>
                      )
                    })}
                    {status === 'running' && (
                      <li className="timeline__item timeline__item--info">
                        <span className="timeline__time muted">Đang chạy</span>
                        <span className="timeline__icon"><PlayIcon /></span>
                        <span className="timeline__text muted">Agent đang chạy…</span>
                      </li>
                    )}
                    {status === 'awaiting_approval' && (
                      <li className="timeline__item timeline__item--warning">
                        <span className="timeline__time muted">Tạm dừng</span>
                        <span className="timeline__icon"><LockIcon /></span>
                        <span className="timeline__text">Đang tạm dừng chờ người duyệt (Approval Gate)…</span>
                      </li>
                    )}
                  </ol>
                )}
              </section>
            </aside>
          </div>
        )}

        {tab === 'uc09' && runId && runUc === 'uc09' && events.length > 0 && (
          <div className="results-stage">
            <CalendarView
              runId={runId}
              events={events}
              canResume={status !== 'running' && status !== 'done'}
              onApprove={handleApproveUC09}
              onResume={() => handleResumeUC09(runId)}
            />
          </div>
        )}

        {output && tab === 'uc01' && Boolean(output.prompt_set) && (
          <div className="results-stage">
            <ProfileView profile={output.brand_profile as BrandProfile} />
            <PromptTable promptSet={output.prompt_set as PromptSet} />
          </div>
        )}

        {output && tab === 'uc03' && Boolean(output.article) && (
          <div className="results-stage">
            <ArticleView article={output.article as Article} />
          </div>
        )}

        {output && tab === 'uc02' && Boolean(output.report) && (
          <div className="results-stage">
            <ResearchReportView report={output.report as ResearchReport} events={events} />
          </div>
        )}

        {output && tab === 'uc04' && Boolean(output.report) && (
          <div className="results-stage">
            <FactCheckPanel report={output.report as ClaimReport} />
          </div>
        )}
      </main>
    </>
  )
}
