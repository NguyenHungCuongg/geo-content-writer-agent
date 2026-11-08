// Kiểu dữ liệu chép từ agent/schemas.py và hai lời gọi tới backend (app/backend/main.py).

export type TraceEvent = { ts: string; run_id: string; event: string; [key: string]: unknown }

export type Intent = 'informational' | 'navigational' | 'commercial' | 'transactional'

export type Product = { name: string; attributes: string[]; price: string | null }

export type BrandProfile = {
  name: string
  about: string | null
  mission: string | null
  service_area: string[]
  products: Product[]
  personas: string[]
  brand_voice: string | null
  competitors: string[]
  missing_info: string[]
  clarifying_questions: string[]
  unverified_claims: string[]
  sources: Record<string, string>
}

export type Prompt = {
  id: string
  text: string
  intent: Intent
  topic: string
  persona: string
  keywords: string[]
  mentions_brand: boolean
}

export type PromptSet = { prompts: Prompt[] }

const TERMINAL = new Set(['output', 'error'])

export async function startRun(brief: string, topics: string[]): Promise<string> {
  let res: Response
  try {
    res = await fetch('/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brief, topics }),
    })
  } catch {
    throw new Error('Không kết nối được backend. Kiểm tra uvicorn đang chạy ở cổng 8000.')
  }
  if (res.status === 422) {
    throw new Error('Dữ liệu gửi lên không hợp lệ (brief tối đa 20.000 ký tự).')
  }
  if (!res.ok) throw new Error(`Backend trả lỗi ${res.status}.`)
  const { run_id } = (await res.json()) as { run_id: string }
  return run_id
}

/** Theo dõi một run. Đóng kết nối khi có event kết thúc, nếu không trình duyệt sẽ tự kết nối lại. */
export function watchRun(
  runId: string,
  onEvent: (e: TraceEvent) => void,
  onLost: () => void,
): () => void {
  const source = new EventSource(`/runs/${runId}/events`)
  source.onmessage = (message) => {
    const event = JSON.parse(message.data) as TraceEvent
    onEvent(event)
    if (TERMINAL.has(event.event)) source.close()
  }
  source.onerror = () => {
    source.close()
    onLost()
  }
  return () => source.close()
}

export type Citation = {
  n: number
  chunk_id: string
  url: string
  quote: string
}

export type ResearchAnswer = {
  question: string
  answer: string
  citations: Citation[]
  insufficient: boolean
}

export type ResearchReport = {
  topic: string
  queries: string[]
  answers: ResearchAnswer[]
}

export async function startRunUC02(topic: string, questions: string[]): Promise<string> {
  let res: Response
  try {
    res = await fetch('/runs/uc02', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, questions }),
    })
  } catch {
    throw new Error('Không kết nối được backend. Kiểm tra uvicorn đang chạy ở cổng 8000.')
  }
  if (res.status === 422) {
    throw new Error('Dữ liệu gửi lên không hợp lệ.')
  }
  if (!res.ok) throw new Error(`Backend trả lỗi ${res.status}.`)
  const { run_id } = (await res.json()) as { run_id: string }
  return run_id
}

// ------------------------------------------------------------------ UC-03 (agent/article.py)

export type SectionFormat = 'paragraph' | 'list' | 'steps' | 'table'

export type Section = {
  heading: string
  level: 2 | 3
  answer_first: string
  points: string[]
  format: SectionFormat
  needs_citation: boolean
  prompt_ids: string[]
}

export type FAQItem = { question: string; answer: string; prompt_ids: string[] }

export type OutlinePlan = {
  title: string
  meta_description: string
  primary_keyword: string
  secondary_keywords: string[]
  target_prompts: string[]
  sections: Section[]
  faq: FAQItem[]
}

export type Article = {
  outline: OutlinePlan
  markdown: string
  citations: Citation[]
  notes: string[]
}

export async function startRunUC03(topic: string, prompts: Prompt[]): Promise<string> {
  let res: Response
  try {
    res = await fetch('/runs/uc03', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, prompts }),
    })
  } catch {
    throw new Error('Không kết nối được backend. Kiểm tra uvicorn đang chạy ở cổng 8000.')
  }
  if (res.status === 422) {
    throw new Error('Dữ liệu gửi lên không hợp lệ (cần chủ đề và ít nhất 1 prompt).')
  }
  if (!res.ok) throw new Error(`Backend trả lỗi ${res.status}.`)
  const { run_id } = (await res.json()) as { run_id: string }
  return run_id
}

export type Evidence = {
  chunk_id: string | null
  url: string
  quote: string
  trust_tier: 'A' | 'B' | 'C' | 'brand'
  stance: 'supports' | 'contradicts'
}

export type Location = {
  heading: string
  paragraph: number
}

export type ClaimVerdict = {
  claim: string
  location: Location
  has_number: boolean
  verdict: 'supported' | 'contradicted' | 'unverifiable'
  evidence: Evidence[]
  action: 'keep' | 'rewrite' | 'remove'
}

export type ClaimReport = {
  claims: ClaimVerdict[]
  round: number
}

export async function startRunUC04(article: Article): Promise<string> {
  let res: Response
  try {
    res = await fetch('/runs/uc04', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ article }),
    })
  } catch {
    throw new Error('Không kết nối được backend. Kiểm tra uvicorn đang chạy ở cổng 8000.')
  }
  if (!res.ok) throw new Error(`Backend trả lỗi ${res.status}.`)
  const { run_id } = (await res.json()) as { run_id: string }
  return run_id
}

/** Lấy PromptSet từ trace của một run UC-01 đã xong (backend phát lại trace qua /events). */
export function loadPromptSet(runId: string): Promise<PromptSet> {
  return new Promise((resolve, reject) => {
    let settled = false
    const close = watchRun(
      runId,
      (event) => {
        if (settled) return
        if (event.event === 'output' && event.prompt_set) {
          settled = true
          resolve(event.prompt_set as PromptSet)
          close()
        } else if (event.event === 'output' || event.event === 'error') {
          settled = true
          reject(new Error(`Run ${runId} không có PromptSet (không phải run UC-01 thành công).`))
          close()
        }
      },
      () => {
        if (!settled) reject(new Error(`Không tìm thấy run ${runId}.`))
      },
    )
  })
}
