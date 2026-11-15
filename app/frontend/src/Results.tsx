import { useState } from 'react'
import type { BrandProfile, Intent, PromptSet } from './api'
import { AlertIcon, CheckIcon } from './Icons'

const INTENTS: Intent[] = ['informational', 'navigational', 'commercial', 'transactional']

const percent = (n: number, total: number) => (total ? Math.round((n / total) * 100) : 0)

function Field({ label, value }: { label: string; value: string | null | string[] }) {
  const text = Array.isArray(value) ? value.join(', ') : value
  return (
    <div className="meta-row">
      <dt>{label}</dt>
      <dd>{text || <span className="muted">(brief không nói)</span>}</dd>
    </div>
  )
}

// Chuỗi do LLM sinh có thể trùng nhau, nên key là vị trí chứ không phải nội dung.
function Items({ items }: { items: string[] }) {
  return <ul className="inline-list">{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
}

export function ProfileView({ profile }: { profile: BrandProfile }) {
  const sources = Object.entries(profile.sources)
  return (
    <section className="section-block">
      <h2>Hồ sơ thương hiệu: {profile.name}</h2>

      {profile.missing_info.length > 0 && (
        <div className="alert alert--warning">
          <div className="alert__head">
            <AlertIcon />
            <h3>Brief còn thiếu thông tin</h3>
          </div>
          <Items items={profile.missing_info} />
          <h4>Câu hỏi làm rõ</h4>
          <Items items={profile.clarifying_questions} />
        </div>
      )}

      {profile.unverified_claims.length > 0 && (
        <div className="alert alert--warning">
          <div className="alert__head">
            <AlertIcon />
            <h3>Khẳng định cần chứng minh</h3>
          </div>
          <Items items={profile.unverified_claims} />
        </div>
      )}

      <dl className="meta-grid">
        <Field label="Giới thiệu" value={profile.about} />
        <Field label="Sứ mệnh" value={profile.mission} />
        <Field label="Khu vực phục vụ" value={profile.service_area} />
        <Field label="Persona" value={profile.personas} />
        <Field label="Giọng văn" value={profile.brand_voice} />
        <Field label="Đối thủ" value={profile.competitors} />
      </dl>

      {profile.products.length > 0 && (
        <div className="scroll">
          <table className="responsive-table">
            <thead>
              <tr><th>Sản phẩm</th><th>Thuộc tính</th><th>Giá</th></tr>
            </thead>
            <tbody>
              {profile.products.map((p, i) => (
                <tr key={i}>
                  <td data-label="Sản phẩm"><strong>{p.name}</strong></td>
                  <td data-label="Thuộc tính">{p.attributes.join('; ')}</td>
                  <td data-label="Giá" className="num">{p.price ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <details>
        <summary>Câu trích từ brief (<span className="num">{sources.length}</span>)</summary>
        <div className="scroll">
          <table>
            <tbody>
              {sources.map(([field, quote]) => (
                <tr key={field}><td><code>{field}</code></td><td>{quote}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}

export function PromptTable({ promptSet }: { promptSet: PromptSet }) {
  const [intent, setIntent] = useState<Intent | 'all'>('all')
  const prompts = promptSet.prompts
  const total = prompts.length
  const branded = prompts.filter((p) => p.mentions_brand).length
  const shown = intent === 'all' ? prompts : prompts.filter((p) => p.intent === intent)

  return (
    <section className="section-block">
      <div className="section-head">
        <h2>Tập prompt</h2>
        <label className="filter-bar">
          <span className="field-label">Lọc theo intent</span>
          <select value={intent} onChange={(e) => setIntent(e.target.value as Intent | 'all')}>
            <option value="all">Tất cả intent</option>
            {INTENTS.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
        </label>
      </div>

      <dl className="stat-strip stat-strip--6 ticks" aria-label="Phân bố tập prompt">
        <div className="stat-strip__item">
          <dt>Tổng số prompt</dt>
          <dd className="num">{total}</dd>
        </div>
        {INTENTS.map((item) => {
          const n = prompts.filter((p) => p.intent === item).length
          return (
            <div className="stat-strip__item" key={item}>
              <dt>{item}</dt>
              <dd className="num">{n} ({percent(n, total)}%)</dd>
            </div>
          )
        })}
        <div className="stat-strip__item">
          <dt>Nhắc thương hiệu</dt>
          <dd className="num">{branded} ({percent(branded, total)}%)</dd>
        </div>
      </dl>

      <div className="scroll">
        <table className="responsive-table">
          <thead>
            <tr>
              <th>ID</th><th>Câu hỏi</th><th>Intent</th><th>Chủ đề</th>
              <th>Persona</th><th>Từ khoá</th><th>Nhắc thương hiệu</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={p.id}>
                <td data-label="ID" className="num"><code>{p.id}</code></td>
                <td data-label="Câu hỏi">{p.text}</td>
                <td data-label="Intent"><span className="badge">{p.intent}</span></td>
                <td data-label="Chủ đề">{p.topic}</td>
                <td data-label="Persona">{p.persona}</td>
                <td data-label="Từ khoá">{p.keywords.join(', ')}</td>
                <td data-label="Nhắc thương hiệu">
                  {p.mentions_brand ? (
                    <span className="stance--supports" title="Có nhắc thương hiệu">
                      <CheckIcon />
                      <span className="visually-hidden">Có nhắc thương hiệu</span>
                    </span>
                  ) : (
                    <span className="muted">Không</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function ResearchReportView({
  report,
  events,
}: {
  report: import('./api').ResearchReport
  events: import('./api').TraceEvent[]
}) {
  const ingestCalls = events
    .filter((e) => e.event === 'tool_call' && e.name === 'kb_ingest')
    .map((e) => {
      const data = (e.data as Record<string, any>) || {}
      return {
        url: data.url || (e.args as Record<string, any>)?.url || '',
        chunks: data.chunks ?? 0,
        suspicious: data.suspicious ?? 0,
        duplicate: data.duplicate ?? false,
        trust_tier: data.trust_tier || (e.args as Record<string, any>)?.trust_tier || 'C',
      }
    })

  return (
    <section className="section-block">
      <h2>Báo cáo nghiên cứu: {report.topic}</h2>

      <div className="panel">
        <div className="panel__head">
          <h3>Truy vấn con đã thực hiện (<span className="num">{report.queries.length}</span>)</h3>
        </div>
        <ul className="inline-list">
          {report.queries.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ul>
      </div>

      {ingestCalls.length > 0 && (
        <div className="section-block">
          <h3>Nguồn đã nạp vào kho tri thức (<span className="num">{ingestCalls.length}</span>)</h3>
          <div className="scroll">
            <table className="responsive-table">
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Tier</th>
                  <th>Số chunks</th>
                  <th>Cờ nghi vấn</th>
                  <th>Trùng lặp</th>
                </tr>
              </thead>
              <tbody>
                {ingestCalls.map((ing, i) => (
                  <tr key={i}>
                    <td data-label="URL">
                      <code className="url-break">{ing.url}</code>
                    </td>
                    <td data-label="Tier">
                      <span className="badge">Tier {ing.trust_tier}</span>
                    </td>
                    <td data-label="Số chunks" className="num">{ing.chunks}</td>
                    <td data-label="Cờ nghi vấn">
                      {ing.suspicious > 0 ? (
                        <span className="status-pill status-pill--failed">
                          <AlertIcon />
                          <span>Nghi vấn (<span className="num">{ing.suspicious}</span>)</span>
                        </span>
                      ) : (
                        <span className="status-pill status-pill--approved">An toàn</span>
                      )}
                    </td>
                    <td data-label="Trùng lặp">{ing.duplicate ? 'Có' : 'Không'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="section-block">
        <h3>Câu trả lời nghiên cứu (<span className="num">{report.answers.length}</span>)</h3>
        <div className="qa-list">
          {report.answers.map((ans, i) => (
            <article key={i} className="qa-item">
              <div className="qa-item__q">
                <span className="num">Q{i + 1}:</span> {ans.question}
              </div>
              <div className="qa-item__a">
                {ans.insufficient ? (
                  <span className="qa-item__insufficient">[Không đủ nguồn] {ans.answer}</span>
                ) : (
                  ans.answer
                )}
              </div>

              {ans.citations && ans.citations.length > 0 && (
                <div className="qa-citations">
                  <div className="muted">Trích dẫn:</div>
                  <ul>
                    {ans.citations.map((c) => (
                      <li key={c.n}>
                        <strong className="num">[{c.n}]</strong>{' '}
                        <a href={c.url} target="_blank" rel="noreferrer" className="url-break">
                          {c.url}
                        </a>
                        <span>: "{c.quote}"</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
