import { useState } from 'react'
import type { BrandProfile, Intent, PromptSet } from './api'

const INTENTS: Intent[] = ['informational', 'navigational', 'commercial', 'transactional']

const percent = (n: number, total: number) => (total ? Math.round((n / total) * 100) : 0)

function Field({ label, value }: { label: string; value: string | null | string[] }) {
  const text = Array.isArray(value) ? value.join(', ') : value
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd>{text || <span className="muted">(brief không nói)</span>}</dd>
    </div>
  )
}

// Chuỗi do LLM sinh có thể trùng nhau, nên key là vị trí chứ không phải nội dung.
function Items({ items }: { items: string[] }) {
  return <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
}

export function ProfileView({ profile }: { profile: BrandProfile }) {
  const sources = Object.entries(profile.sources)
  return (
    <section>
      <h2>Hồ sơ thương hiệu: {profile.name}</h2>

      {profile.missing_info.length > 0 && (
        <div className="box warning">
          <h3>Brief còn thiếu thông tin</h3>
          <Items items={profile.missing_info} />
          <h3>Câu hỏi làm rõ</h3>
          <Items items={profile.clarifying_questions} />
        </div>
      )}

      {profile.unverified_claims.length > 0 && (
        <div className="box warning">
          <h3>Khẳng định cần chứng minh</h3>
          <Items items={profile.unverified_claims} />
        </div>
      )}

      <dl>
        <Field label="Giới thiệu" value={profile.about} />
        <Field label="Sứ mệnh" value={profile.mission} />
        <Field label="Khu vực phục vụ" value={profile.service_area} />
        <Field label="Persona" value={profile.personas} />
        <Field label="Giọng văn" value={profile.brand_voice} />
        <Field label="Đối thủ" value={profile.competitors} />
      </dl>

      {profile.products.length > 0 && (
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Sản phẩm</th><th>Thuộc tính</th><th>Giá</th></tr>
            </thead>
            <tbody>
              {profile.products.map((p, i) => (
                <tr key={i}>
                  <td>{p.name}</td>
                  <td>{p.attributes.join('; ')}</td>
                  <td>{p.price ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <details>
        <summary>Câu trích từ brief ({sources.length})</summary>
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
  const counts = INTENTS.map((i) => {
    const n = prompts.filter((p) => p.intent === i).length
    return `${i} ${n} (${percent(n, total)}%)`
  })
  const shown = intent === 'all' ? prompts : prompts.filter((p) => p.intent === intent)

  return (
    <section>
      <h2>Tập prompt</h2>
      <p>
        {[`${total} prompt`, ...counts, `nhắc thương hiệu ${branded} (${percent(branded, total)}%)`]
          .join(' · ')}
      </p>
      <label>
        Lọc theo intent{' '}
        <select value={intent} onChange={(e) => setIntent(e.target.value as Intent | 'all')}>
          <option value="all">Tất cả intent</option>
          {INTENTS.map((i) => <option key={i} value={i}>{i}</option>)}
        </select>
      </label>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th><th>Câu hỏi</th><th>Intent</th><th>Chủ đề</th>
              <th>Persona</th><th>Từ khoá</th><th>Nhắc thương hiệu</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td>{p.text}</td>
                <td>{p.intent}</td>
                <td>{p.topic}</td>
                <td>{p.persona}</td>
                <td>{p.keywords.join(', ')}</td>
                <td>{p.mentions_brand ? '✓' : ''}</td>
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
      }
    })

  return (
    <section>
      <h2>Báo cáo nghiên cứu: {report.topic}</h2>

      <div className="box">
        <h3>Truy vấn con đã thực hiện ({report.queries.length})</h3>
        <ul>
          {report.queries.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ul>
      </div>

      {ingestCalls.length > 0 && (
        <div className="box">
          <h3>Nguồn đã nạp vào kho tri thức ({ingestCalls.length})</h3>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Số chunks</th>
                  <th>Cờ nghi vấn</th>
                  <th>Trùng lặp</th>
                </tr>
              </thead>
              <tbody>
                {ingestCalls.map((ing, i) => (
                  <tr key={i}>
                    <td>
                      <code>{ing.url}</code>
                    </td>
                    <td>{ing.chunks}</td>
                    <td>
                      {ing.suspicious > 0 ? (
                        <span style={{ color: 'red' }}>⚠️ Nghi vấn ({ing.suspicious})</span>
                      ) : (
                        'An toàn'
                      )}
                    </td>
                    <td>{ing.duplicate ? 'Có' : 'Không'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div>
        <h3>Câu trả lời nghiên cứu ({report.answers.length})</h3>
        {report.answers.map((ans, i) => (
          <div key={i} className="field" style={{ marginBottom: '1.5rem' }}>
            <dt style={{ fontWeight: 'bold' }}>
              Q{i + 1}: {ans.question}
            </dt>
            <dd style={{ marginTop: '0.5rem' }}>
              {ans.insufficient ? (
                <span style={{ color: '#d97706' }}>[Không đủ nguồn] {ans.answer}</span>
              ) : (
                ans.answer
              )}
            </dd>

            {ans.citations && ans.citations.length > 0 && (
              <div style={{ marginTop: '0.5rem', paddingLeft: '1rem', borderLeft: '2px solid #ccc' }}>
                <div style={{ fontSize: '0.9em', color: '#666' }}>Trích dẫn:</div>
                <ul>
                  {ans.citations.map((c) => (
                    <li key={c.n} style={{ fontSize: '0.9em' }}>
                      <strong>[{c.n}]</strong>{' '}
                      <a href={c.url} target="_blank" rel="noreferrer">
                        {c.url}
                      </a>
                      : <em>"{c.quote}"</em>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
