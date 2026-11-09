import { useState } from 'react'
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

const STATUS_META: Record<CalendarStatus, { label: string; bg: string; color: string }> = {
  todo: { label: 'Chờ làm (todo)', bg: '#f3f4f6', color: '#4b5563' },
  researching: { label: 'Đang nghiên cứu (researching)', bg: '#eff6ff', color: '#1d4ed8' },
  drafting: { label: 'Đang viết/sửa (drafting)', bg: '#fef3c7', color: '#b45309' },
  review: { label: 'Chờ duyệt (review)', bg: '#ffedd5', color: '#c2410c' },
  approved: { label: 'Đã duyệt (approved)', bg: '#ecfdf5', color: '#047857' },
  failed: { label: 'Thất bại (failed)', bg: '#fef2f2', color: '#b91c1c' },
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

  const approvedCount = items.filter((i) => i.status === 'approved').length
  const reviewCount = items.filter((i) => i.status === 'review').length
  const failedCount = items.filter((i) => i.status === 'failed').length

  async function handleDecision(decision: 'approve' | 'reject') {
    setActionError(null)
    if (!reviewer.trim()) {
      setActionError('Vui lòng nhập tên người duyệt.')
      return
    }
    if (decision === 'reject' && !reason.trim()) {
      setActionError('Vui lòng nhập lý do từ chối để Writer chỉnh sửa bài viết.')
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
    <section style={{ marginTop: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h2 style={{ margin: 0 }}>Lịch nội dung 4 tuần · UC-09 ({items.length} bài)</h2>
        {canResume && !pendingApproval && (
          <button type="button" onClick={handleResume} disabled={submitting}>
            ▶️ Chạy tiếp từ checkpoint (Resume)
          </button>
        )}
      </div>

      {items.length > 0 && (
        <>
          <p className="muted" style={{ marginTop: '0.4rem' }}>
            Run <code>{runId}</code> · Đã duyệt: <strong>{approvedCount}/{items.length}</strong>
            {reviewCount > 0 && <> · Đang chờ duyệt: <strong>{reviewCount}</strong></>}
            {failedCount > 0 && <> · Thất bại: <strong>{failedCount}</strong></>}
          </p>

          <div className="scroll">
            <table>
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
                      <td><code>{item.id}</code></td>
                      <td>Tuần {item.week}</td>
                      <td><strong>{item.title}</strong></td>
                      <td><code>{item.primary_keyword}</code></td>
                      <td>{item.prompt_ids.join(', ')}</td>
                      <td>{item.internal_links.join(', ')}</td>
                      <td>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '2px 8px',
                            borderRadius: '4px',
                            fontWeight: 600,
                            fontSize: '0.85em',
                            background: meta.bg,
                            color: meta.color,
                          }}
                        >
                          {meta.label}
                        </span>
                      </td>
                      <td>
                        {hasContent ? (
                          <button
                            type="button"
                            className="link"
                            onClick={() => setSelectedItemId(item.id === selectedItemId ? null : item.id)}
                          >
                            {inspectId === item.id ? 'Đang xem' : 'Xem bài'}
                          </button>
                        ) : (
                          <span className="muted">—</span>
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
        <div className="box error" role="alert">
          <p style={{ margin: 0 }}>{actionError}</p>
        </div>
      )}

      {pendingApproval && (
        <div
          className="box"
          style={{
            marginTop: '1.5rem',
            borderColor: '#c2410c',
            background: '#fff7ed',
            padding: '16px',
          }}
        >
          <h3 style={{ marginTop: 0, color: '#9a3412' }}>
            🛑 Cổng phê duyệt của người (Approval Gate): [{pendingApproval.item_id}] {pendingApproval.title}
          </h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Kiểm tra bản xem trước bài viết, trích dẫn và bảng kiểm chứng sự thật (Fact-check) trước khi quyết định duyệt hoặc từ chối.
          </p>

          {pendingApproval.blocking_claims.length > 0 && (
            <div className="box error" role="alert">
              <h4 style={{ margin: '0 0 6px 0' }}>
                🔒 Nút Duyệt đang bị khoá ({pendingApproval.blocking_claims.length} claim số liệu chưa đạt Supported)
              </h4>
              <p style={{ margin: '0 0 6px 0', fontSize: '0.9em' }}>
                Theo quy tắc D-15, bài viết còn khẳng định chứa số liệu chưa được chứng minh bằng nguồn hợp lệ thì không thể duyệt. Vui lòng bấm <strong>Từ chối & Yêu cầu sửa</strong> để Writer viết lại hoặc gỡ số liệu:
              </p>
              <ul style={{ margin: 0, fontSize: '0.9em' }}>
                {pendingApproval.blocking_claims.map((c, idx) => (
                  <li key={idx}>
                    <code>[{c.verdict}]</code> {c.claim}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ display: 'grid', gap: '8px', maxWidth: 640, marginTop: '12px' }}>
            <label htmlFor="approval-reviewer">Người duyệt</label>
            <input
              id="approval-reviewer"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              placeholder="Tên người duyệt (bắt buộc)"
            />

            <label htmlFor="approval-reason">Lý do duyệt / Yêu cầu chỉnh sửa cho Writer</label>
            <textarea
              id="approval-reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Nhập nhận xét hoặc lý do từ chối (từ chối lần 1 quay về Writer sửa bài, từ chối lần 2 bài chuyển sang failed)..."
            />

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '4px' }}>
              <button
                type="button"
                disabled={submitting || pendingApproval.blocking_claims.length > 0}
                onClick={() => handleDecision('approve')}
                style={{
                  background: pendingApproval.blocking_claims.length > 0 ? '#9ca3af' : '#047857',
                }}
                title={
                  pendingApproval.blocking_claims.length > 0
                    ? `Khoá duyệt vì còn ${pendingApproval.blocking_claims.length} claim số liệu chưa được chứng minh`
                    : 'Duyệt bài viết này'
                }
              >
                {pendingApproval.blocking_claims.length > 0
                  ? `🔒 Đang khoá Duyệt (${pendingApproval.blocking_claims.length} claim chặn)`
                  : '✅ Duyệt bài (Approve)'}
              </button>

              <button
                type="button"
                disabled={submitting}
                onClick={() => handleDecision('reject')}
                style={{ background: '#b91c1c' }}
              >
                ↩️ Từ chối & Yêu cầu sửa (Reject)
              </button>
            </div>
          </div>
        </div>
      )}

      {inspectId && (inspectReport || inspectArticle) && (
        <div style={{ marginTop: '1.5rem' }}>
          <h3>
            Xem trước bài [{inspectId}]{' '}
            {inspectArticle ? `· ${inspectArticle.outline.title}` : ''}
          </h3>
          {inspectReport && <FactCheckPanel report={inspectReport} />}
          {inspectArticle && <ArticleView article={inspectArticle} />}
        </div>
      )}
    </section>
  )
}
