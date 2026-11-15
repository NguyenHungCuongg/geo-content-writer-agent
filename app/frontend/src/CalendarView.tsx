import { useRef, useState } from 'react'
import type {
  ApprovalDecision,
  Article,
  CalendarItem,
  CalendarStatus,
  ClaimReport,
  ClaimVerdict,
  PendingApproval,
  TraceEvent,
} from './api'
import { ArticleView } from './ArticleView'
import { FactCheckPanel } from './FactCheckPanel'
import { AlertIcon, CheckIcon, LockIcon, PlayIcon, ReturnIcon, ShieldIcon } from './Icons'

const STATUS_META: Record<CalendarStatus, { label: string; cls: string }> = {
  todo: { label: 'Chờ làm (todo)', cls: 'status-pill--todo' },
  researching: { label: 'Đang nghiên cứu (researching)', cls: 'status-pill--researching' },
  drafting: { label: 'Đang viết/sửa (drafting)', cls: 'status-pill--drafting' },
  review: { label: 'Chờ duyệt (review)', cls: 'status-pill--review' },
  approved: { label: 'Đã duyệt (approved)', cls: 'status-pill--approved' },
  failed: { label: 'Thất bại (failed)', cls: 'status-pill--failed' },
}

export type DerivedUC09 = {
  items: CalendarItem[]
  articles: Record<string, Article>
  reports: Record<string, ClaimReport>
  pendingApproval: PendingApproval | null
}

/** Tổng hợp trạng thái lịch 8 bài, bài viết và yêu cầu chờ duyệt từ chuỗi SSE trace events. */
export function deriveUC09State(events: TraceEvent[]): DerivedUC09 {
  const itemMap = new Map<string, CalendarItem>()
  const articles: Record<string, Article> = {}
  const reports: Record<string, ClaimReport> = {}
  let latestAwait: PendingApproval | null = null
  let awaitCount = 0
  let approvalCount = 0

  const applyCalendar = (cal: unknown) => {
    const rawItems = (cal as { items?: CalendarItem[] } | undefined)?.items
    if (!Array.isArray(rawItems)) return
    for (const it of rawItems) {
      if (it && typeof it.id === 'string') {
        itemMap.set(it.id, { ...it })
      }
    }
  }

  for (const e of events) {
    const d = e as Record<string, unknown>
    if (d.calendar) {
      applyCalendar(d.calendar)
    }
    if (e.event === 'node') {
      const itemId = typeof d.item_id === 'string' ? d.item_id : null
      const name = typeof d.name === 'string' ? d.name : ''
      const status = typeof d.status === 'string' ? d.status : ''
      if (itemId && itemMap.has(itemId)) {
        const cur = itemMap.get(itemId)!
        if (status === 'start') {
          if (name === 'research') itemMap.set(itemId, { ...cur, status: 'researching' })
          if (name === 'write') itemMap.set(itemId, { ...cur, status: 'drafting' })
        } else if (status === 'error' && name !== 'approve') {
          itemMap.set(itemId, { ...cur, status: 'failed' })
        }
      }
    }
    if (e.event === 'decision' && d.action === 'await_approval') {
      awaitCount += 1
      const itemId = String(d.item_id ?? '')
      const title = String(d.title ?? '')
      const article = d.article as Article | undefined
      const claimReport = d.claim_report as ClaimReport | undefined
      const blockingClaims = Array.isArray(d.blocking_claims)
        ? (d.blocking_claims as ClaimVerdict[])
        : claimReport
          ? claimReport.claims.filter((c) => c.has_number && c.verdict !== 'supported')
          : []
      if (itemId && article) articles[itemId] = article
      if (itemId && claimReport) reports[itemId] = claimReport
      if (itemId && itemMap.has(itemId)) {
        itemMap.set(itemId, { ...itemMap.get(itemId)!, status: 'review' })
      }
      latestAwait = {
        item_id: itemId,
        title,
        article,
        claim_report: claimReport,
        blocking_claims: blockingClaims,
      }
    }
    if (e.event === 'decision' && d.action === 'approval') {
      approvalCount += 1
      const itemId = String(d.item_id ?? '')
      const dec = String(d.decision ?? '')
      if (itemId && itemMap.has(itemId)) {
        const cur = itemMap.get(itemId)!
        if (dec === 'approve') {
          itemMap.set(itemId, { ...cur, status: 'approved' })
        } else if (dec === 'reject') {
          itemMap.set(itemId, { ...cur, status: 'drafting' })
        }
      }
    }
    if (e.event === 'output' && d.articles && typeof d.articles === 'object') {
      for (const [k, v] of Object.entries(d.articles as Record<string, Article>)) {
        articles[k] = v
      }
    }
  }

  return {
    items: Array.from(itemMap.values()),
    articles,
    reports,
    pendingApproval: awaitCount > approvalCount ? latestAwait : null,
  }
}

export function CalendarView({
  runId,
  events,
  canResume,
  onApprove,
  onResume,
}: {
  runId: string
  events: TraceEvent[]
  canResume: boolean
  onApprove: (decision: ApprovalDecision) => Promise<void>
  onResume: () => Promise<void>
}) {
  const { items, articles, reports, pendingApproval } = deriveUC09State(events)
  const [reviewer, setReviewer] = useState('Biên tập viên')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [invalidField, setInvalidField] = useState<'reviewer' | 'reason' | null>(null)
  const reviewerRef = useRef<HTMLInputElement | null>(null)
  const reasonRef = useRef<HTMLTextAreaElement | null>(null)

  const approvedCount = items.filter((i) => i.status === 'approved').length
  const reviewCount = items.filter((i) => i.status === 'review').length
  const failedCount = items.filter((i) => i.status === 'failed').length
  const reviewerInvalid = invalidField === 'reviewer' && !reviewer.trim()
  const reasonInvalid = invalidField === 'reason' && !reason.trim()

  async function handleDecision(decision: 'approve' | 'reject') {
    setActionError(null)
    setInvalidField(null)
    if (!reviewer.trim()) {
      setActionError('Vui lòng nhập tên người duyệt.')
      setInvalidField('reviewer')
      reviewerRef.current?.focus()
      return
    }
    if (decision === 'reject' && !reason.trim()) {
      setActionError('Vui lòng nhập lý do từ chối để Writer chỉnh sửa bài viết.')
      setInvalidField('reason')
      reasonRef.current?.focus()
      return
    }
    setSubmitting(true)
    try {
      await onApprove({
        decision,
        reviewer: reviewer.trim(),
        reason: reason.trim() || (decision === 'approve' ? 'Đạt yêu cầu xuất bản' : 'Cần chỉnh sửa'),
      })
      setReason('')
    } catch (err) {
      setActionError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleResume() {
    setActionError(null)
    setSubmitting(true)
    try {
      await onResume()
    } catch (err) {
      setActionError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const inspectId = pendingApproval?.item_id ?? selectedItemId
  const inspectArticle = inspectId ? articles[inspectId] : undefined
  const inspectReport = inspectId ? reports[inspectId] : undefined

  return (
    <section className="section-block">
      <div className="section-head">
        <h2>Lịch nội dung 4 tuần, UC-09 ({items.length} bài)</h2>
        {canResume && !pendingApproval && (
          <button
            type="button"
            className="btn btn--quiet"
            onClick={handleResume}
            disabled={submitting}
            aria-busy={submitting}
          >
            <PlayIcon />
            <span>Chạy tiếp từ checkpoint (Resume)</span>
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <p className="muted">Đang khởi tạo lịch nội dung 4 tuần…</p>
      ) : (
        <>
          <dl className="stat-strip ticks" aria-label="Tổng quan lịch nội dung">
            <div className="stat-strip__item">
              <dt>Mã Run</dt>
              <dd className="num" title={runId}>{runId.slice(0, 12)}</dd>
            </div>
            <div className="stat-strip__item">
              <dt>Đã duyệt</dt>
              <dd className="num">{approvedCount}/{items.length}</dd>
            </div>
            <div className="stat-strip__item">
              <dt>Đang chờ duyệt</dt>
              <dd className="num">{reviewCount}</dd>
            </div>
            <div className="stat-strip__item">
              <dt>Thất bại</dt>
              <dd className="num">{failedCount}</dd>
            </div>
          </dl>

          <div className="scroll">
            <table className="responsive-table">
              <thead>
                <tr>
                  <th>Mã bài</th>
                  <th>Tuần</th>
                  <th>Tiêu đề dự kiến</th>
                  <th>Từ khoá chính</th>
                  <th>Prompt</th>
                  <th>Liên kết nội bộ</th>
                  <th>Trạng thái</th>
                  <th>Chi tiết</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const meta = STATUS_META[item.status] ?? STATUS_META.todo
                  const hasContent = Boolean(articles[item.id] || reports[item.id])
                  return (
                    <tr key={item.id}>
                      <td data-label="Mã bài"><code className="num">{item.id}</code></td>
                      <td data-label="Tuần" className="num">Tuần {item.week}</td>
                      <td data-label="Tiêu đề dự kiến"><strong>{item.title}</strong></td>
                      <td data-label="Từ khoá chính"><code>{item.primary_keyword}</code></td>
                      <td data-label="Prompt" className="num">{item.prompt_ids.join(', ')}</td>
                      <td data-label="Liên kết nội bộ">{item.internal_links.join(', ')}</td>
                      <td data-label="Trạng thái">
                        <span className={`status-pill ${meta.cls}`}>
                          <span>{meta.label}</span>
                        </span>
                      </td>
                      <td data-label="Chi tiết">
                        {hasContent ? (
                          <button
                            type="button"
                            className="link"
                            onClick={() => setSelectedItemId(item.id === selectedItemId ? null : item.id)}
                          >
                            {inspectId === item.id ? 'Đang xem' : 'Xem bài'}
                          </button>
                        ) : (
                          <span className="muted">Chưa có</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {actionError && (
        <div id="approval-error" className="alert alert--error" role="alert">
          <div className="alert__head">
            <AlertIcon />
            <p>{actionError}</p>
          </div>
        </div>
      )}

      {pendingApproval && (
        <div className="approval-gate">
          <div className="alert__head">
            <ShieldIcon />
            <h3>
              Cổng phê duyệt của người (Approval Gate): [{pendingApproval.item_id}] {pendingApproval.title}
            </h3>
          </div>
          <p className="muted">
            Kiểm tra bản xem trước bài viết, trích dẫn và bảng kiểm chứng sự thật (Fact-check) trước khi quyết định duyệt hoặc từ chối.
          </p>

          {pendingApproval.blocking_claims.length > 0 && (
            <div className="approval-gate__blocker" role="alert">
              <div className="alert__head">
                <LockIcon />
                <h4>
                  Nút Duyệt đang bị khoá ({pendingApproval.blocking_claims.length} claim số liệu chưa đạt Supported)
                </h4>
              </div>
              <p>
                Theo quy tắc D-15, bài viết còn khẳng định chứa số liệu chưa được chứng minh bằng nguồn hợp lệ thì không thể duyệt. Vui lòng bấm <strong>Từ chối & Yêu cầu sửa</strong> để Writer viết lại hoặc gỡ số liệu:
              </p>
              <ul className="inline-list">
                {pendingApproval.blocking_claims.map((c, idx) => (
                  <li key={idx}>
                    <code>[{c.verdict}]</code> {c.claim}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="approval-gate__form">
            <div className="field-group">
              <label className="field-label" htmlFor="approval-reviewer">Người duyệt</label>
              <input
                ref={reviewerRef}
                id="approval-reviewer"
                value={reviewer}
                aria-invalid={reviewerInvalid || undefined}
                aria-describedby={actionError && reviewerInvalid ? 'approval-error' : undefined}
                onChange={(e) => setReviewer(e.target.value)}
                placeholder="Tên người duyệt (bắt buộc)"
              />
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="approval-reason">Lý do duyệt / Yêu cầu chỉnh sửa cho Writer</label>
              <textarea
                ref={reasonRef}
                id="approval-reason"
                rows={3}
                value={reason}
                aria-invalid={reasonInvalid || undefined}
                aria-describedby={actionError && reasonInvalid ? 'approval-error' : undefined}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Nhập nhận xét hoặc lý do từ chối (từ chối lần 1 quay về Writer sửa bài, từ chối lần 2 bài chuyển sang failed)..."
              />
            </div>

            <div className="form-actions">
              <button
                type="button"
                className="btn btn--primary"
                disabled={submitting || pendingApproval.blocking_claims.length > 0}
                onClick={() => handleDecision('approve')}
                title={
                  pendingApproval.blocking_claims.length > 0
                    ? `Khoá duyệt vì còn ${pendingApproval.blocking_claims.length} claim số liệu chưa được chứng minh`
                    : 'Duyệt bài viết này'
                }
              >
                {pendingApproval.blocking_claims.length > 0 ? <LockIcon /> : <CheckIcon />}
                <span>
                  {pendingApproval.blocking_claims.length > 0
                    ? `Đang khoá Duyệt (${pendingApproval.blocking_claims.length} claim chặn)`
                    : 'Duyệt bài (Approve)'}
                </span>
              </button>

              <button
                type="button"
                className="btn btn--danger"
                disabled={submitting}
                onClick={() => handleDecision('reject')}
              >
                <ReturnIcon />
                <span>Từ chối & Yêu cầu sửa (Reject)</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {inspectId && (inspectReport || inspectArticle) && (
        <div className="section-block">
          <h2>
            Xem trước bài [{inspectId}]
            {inspectArticle ? `: ${inspectArticle.outline.title}` : ''}
          </h2>
          {inspectReport && <FactCheckPanel report={inspectReport} baseHeadingLevel={3} />}
          {inspectArticle && <ArticleView article={inspectArticle} baseHeadingLevel={3} />}
        </div>
      )}
    </section>
  )
}
