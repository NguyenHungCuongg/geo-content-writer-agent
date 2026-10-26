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
