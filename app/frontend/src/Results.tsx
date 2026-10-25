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

export function ProfileView({ profile }: { profile: BrandProfile }) {
  const sources = Object.entries(profile.sources)
  return (
    <section>
      <h2>Hồ sơ thương hiệu: {profile.name}</h2>

      {profile.missing_info.length > 0 && (
        <div className="box warning">
          <h3>Brief còn thiếu thông tin</h3>
          <ul>{profile.missing_info.map((item) => <li key={item}>{item}</li>)}</ul>
          <h3>Câu hỏi làm rõ</h3>
          <ul>{profile.clarifying_questions.map((q) => <li key={q}>{q}</li>)}</ul>
        </div>
      )}

      {profile.unverified_claims.length > 0 && (
        <div className="box warning">
          <h3>Khẳng định cần chứng minh</h3>
          <ul>{profile.unverified_claims.map((c) => <li key={c}>{c}</li>)}</ul>
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
              {profile.products.map((p) => (
                <tr key={p.name}>
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
