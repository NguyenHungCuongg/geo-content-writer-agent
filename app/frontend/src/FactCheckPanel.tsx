import type { ClaimReport, ClaimVerdict } from './api'

const VERDICT_COLORS: Record<ClaimVerdict['verdict'], { bg: string; color: string; label: string }> = {
  supported: { bg: '#ecfdf5', color: '#047857', label: 'Supported (Hợp lệ)' },
  contradicted: { bg: '#fef2f2', color: '#b91c1c', label: 'Contradicted (Mâu thuẫn)' },
  unverifiable: { bg: '#fffbeb', color: '#b45309', label: 'Unverifiable (Chưa chứng minh)' },
}

export function FactCheckPanel({ report }: { report: ClaimReport }) {
  const blocking = report.claims.filter((c) => c.has_number && c.verdict !== 'supported')

  return (
    <section className="uc04-panel">
      <h2>Báo cáo Fact-check (Vòng {report.round})</h2>

      {blocking.length > 0 ? (
        <div className="box warning" style={{ marginBottom: '1rem', borderLeft: '4px solid #b91c1c' }}>
          <h3 style={{ color: '#b91c1c', margin: '0 0 0.5rem 0' }}>
            ⚠️ Có {blocking.length} claim số liệu chưa đạt Supported (Đang khoá xuất bản)
          </h3>
          <p style={{ margin: 0, fontSize: '0.9em' }}>
            Các claim có số liệu bắt buộc phải được chứng minh bằng ít nhất 1 nguồn Tier A hoặc 2 nguồn Tier B độc lập.
          </p>
        </div>
      ) : (
        <div className="box" style={{ marginBottom: '1rem', borderLeft: '4px solid #047857', background: '#ecfdf5' }}>
          <h3 style={{ color: '#047857', margin: 0 }}>
            ✅ Toàn bộ claim số liệu đã được chứng minh (Đủ điều kiện duyệt)
          </h3>
        </div>
      )}

      <div className="scroll">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9em' }}>
          <thead>
            <tr style={{ background: '#f3f4f6', textAlign: 'left' }}>
              <th style={{ padding: '8px' }}>Khẳng định (Claim)</th>
              <th style={{ padding: '8px' }}>Vị trí</th>
              <th style={{ padding: '8px' }}>Có số</th>
              <th style={{ padding: '8px' }}>Phán quyết</th>
              <th style={{ padding: '8px' }}>Bằng chứng & Nguồn</th>
            </tr>
          </thead>
          <tbody>
            {report.claims.map((c, i) => {
              const meta = VERDICT_COLORS[c.verdict]
              return (
                <tr key={i} style={{ borderBottom: '1px solid #e5e7eb', background: meta.bg }}>
                  <td style={{ padding: '8px', verticalAlign: 'top', fontWeight: 500 }}>
                    {c.claim}
                  </td>
                  <td style={{ padding: '8px', verticalAlign: 'top', color: '#6b7280', fontSize: '0.85em' }}>
                    {c.location.heading ? `${c.location.heading} (đoạn ${c.location.paragraph})` : `Mở đầu (đoạn ${c.location.paragraph})`}
                  </td>
                  <td style={{ padding: '8px', verticalAlign: 'top', textAlign: 'center' }}>
                    {c.has_number ? '🔢' : '—'}
                  </td>
                  <td style={{ padding: '8px', verticalAlign: 'top' }}>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontWeight: 'bold',
                        color: meta.color,
                        background: '#ffffff',
                        border: `1px solid ${meta.color}`,
                        fontSize: '0.85em',
                      }}
                    >
                      {meta.label}
                    </span>
                  </td>
                  <td style={{ padding: '8px', verticalAlign: 'top' }}>
                    {c.evidence && c.evidence.length > 0 ? (
                      <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
                        {c.evidence.map((ev, ei) => (
                          <li key={ei} style={{ marginBottom: '4px' }}>
                            <span className="badge" style={{ marginRight: '4px' }}>Tier {ev.trust_tier}</span>
                            <span style={{ fontSize: '0.8em', color: ev.stance === 'supports' ? '#047857' : '#b91c1c' }}>
                              [{ev.stance}]
                            </span>{' '}
                            <a href={ev.url} target="_blank" rel="noreferrer" style={{ wordBreak: 'break-all' }}>
                              {ev.url}
                            </a>
                            {ev.quote && (
                              <div style={{ color: '#4b5563', fontStyle: 'italic', fontSize: '0.85em', marginTop: '2px' }}>
                                "{ev.quote}"
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span style={{ color: '#9ca3af', fontStyle: 'italic' }}>Không tìm thấy nguồn</span>
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
