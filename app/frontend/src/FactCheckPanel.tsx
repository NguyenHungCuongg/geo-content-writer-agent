import type { ClaimReport, ClaimVerdict } from './api'
import { AlertIcon, CheckIcon, HashIcon } from './Icons'

const VERDICT_META: Record<ClaimVerdict['verdict'], { cls: string; label: string }> = {
  supported: { cls: 'status-pill--approved', label: 'Supported (Hợp lệ)' },
  contradicted: { cls: 'status-pill--failed', label: 'Contradicted (Mâu thuẫn)' },
  unverifiable: { cls: 'status-pill--drafting', label: 'Unverifiable (Chưa chứng minh)' },
}

export function FactCheckPanel({
  report,
  baseHeadingLevel = 2,
}: {
  report: ClaimReport
  baseHeadingLevel?: 2 | 3
}) {
  const blocking = report.claims.filter((c) => c.has_number && c.verdict !== 'supported')
  const SectionHeading = baseHeadingLevel === 3 ? 'h3' : 'h2'
  const AlertHeading = baseHeadingLevel === 3 ? 'h4' : 'h3'

  return (
    <section className="section-block uc04-panel">
      <SectionHeading>Báo cáo Fact-check (Vòng <span className="num">{report.round}</span>)</SectionHeading>

      {blocking.length > 0 ? (
        <div className="alert alert--warning" role="status">
          <div className="alert__head">
            <AlertIcon />
            <AlertHeading>
              Có <span className="num">{blocking.length}</span> claim số liệu chưa đạt Supported (Đang khoá xuất bản)
            </AlertHeading>
          </div>
          <p>
            Các claim có số liệu bắt buộc phải được chứng minh bằng ít nhất 1 nguồn Tier A hoặc 2 nguồn Tier B độc lập.
          </p>
        </div>
      ) : (
        <div className="alert alert--success" role="status">
          <div className="alert__head">
            <CheckIcon />
            <AlertHeading>
              Toàn bộ claim số liệu đã được chứng minh (Đủ điều kiện duyệt)
            </AlertHeading>
          </div>
        </div>
      )}

      <div className="scroll">
        <table className="responsive-table">
          <thead>
            <tr>
              <th>Khẳng định (Claim)</th>
              <th>Vị trí</th>
              <th>Có số</th>
              <th>Phán quyết</th>
              <th>Bằng chứng & Nguồn</th>
            </tr>
          </thead>
          <tbody>
            {report.claims.map((c, i) => {
              const meta = VERDICT_META[c.verdict]
              return (
                <tr key={i}>
                  <td data-label="Khẳng định"><strong>{c.claim}</strong></td>
                  <td data-label="Vị trí" className="muted num">
                    {c.location.heading ? `${c.location.heading} (đoạn ${c.location.paragraph})` : `Mở đầu (đoạn ${c.location.paragraph})`}
                  </td>
                  <td data-label="Có số">
                    {c.has_number ? (
                      <span className="badge" title="Chứa số liệu cần nguồn">
                        <HashIcon />
                        <span className="visually-hidden">Có số liệu</span>
                      </span>
                    ) : (
                      <span className="muted">Không</span>
                    )}
                  </td>
                  <td data-label="Phán quyết">
                    <span className={`status-pill ${meta.cls}`}>
                      {meta.label}
                    </span>
                  </td>
                  <td data-label="Bằng chứng & Nguồn">
                    {c.evidence && c.evidence.length > 0 ? (
                      <ul className="inline-list">
                        {c.evidence.map((ev, ei) => (
                          <li key={ei}>
                            <div className="tag-group">
                              <span className="badge">Tier {ev.trust_tier}</span>
                              <span className={ev.stance === 'supports' ? 'stance--supports' : 'stance--contradicts'}>
                                [{ev.stance}]
                              </span>
                              <a href={ev.url} target="_blank" rel="noreferrer" className="url-break">
                                {ev.url}
                              </a>
                            </div>
                            {ev.quote && (
                              <div className="evidence-quote">
                                "{ev.quote}"
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span className="muted">Không tìm thấy nguồn</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
