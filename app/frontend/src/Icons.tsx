import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

const base: IconProps = {
  width: 16,
  height: 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

/** Biểu tượng 3 vạch nghiêng đặc trưng của Vantage. */
export function BrandMark() {
  return (
    <svg width="20" height="16" viewBox="0 0 20 16" fill="none" aria-hidden="true" className="brand-mark">
      <line x1="2" y1="14" x2="6" y2="2" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square" />
      <line x1="8" y1="14" x2="12" y2="2" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square" />
      <line x1="14" y1="14" x2="18" y2="2" className="brand-mark__live" strokeWidth="2.2" strokeLinecap="square" />
    </svg>
  )
}

export function PlayIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <polygon points="6 4 20 12 6 20 6 4" />
    </svg>
  )
}

export function HistoryIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.5 14" />
    </svg>
  )
}

export function RefreshIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <polyline points="21 3 21 9 15 9" />
    </svg>
  )
}

export function AlertIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <path d="M12 3 2.5 19.5h19L12 3Z" />
      <line x1="12" y1="10" x2="12" y2="14" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

export function ShieldIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <path d="M12 3 4.5 6v6c0 5 3.4 8.6 7.5 9.8 4.1-1.2 7.5-4.8 7.5-9.8V6L12 3Z" />
      <line x1="12" y1="8.5" x2="12" y2="13" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

export function LockIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <rect x="4.5" y="10.5" width="15" height="10" rx="1.5" />
      <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
    </svg>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <polyline points="4.5 12.5 9.5 17.5 19.5 7.5" />
    </svg>
  )
}

export function ReturnIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <polyline points="9 14 4 9 9 4" />
      <path d="M20 19v-6a4 4 0 0 0-4-4H4" />
    </svg>
  )
}

export function BanIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <circle cx="12" cy="12" r="9" />
      <line x1="5.7" y1="5.7" x2="18.3" y2="18.3" />
    </svg>
  )
}

export function CalendarIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <rect x="3.5" y="5" width="17" height="15.5" rx="1.5" />
      <line x1="3.5" y1="10" x2="20.5" y2="10" />
      <line x1="8" y1="3" x2="8" y2="6.5" />
      <line x1="16" y1="3" x2="16" y2="6.5" />
    </svg>
  )
}

export function CompressIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <polyline points="4 14 10 14 10 20" />
      <polyline points="20 10 14 10 14 4" />
      <line x1="14" y1="10" x2="20.5" y2="3.5" />
      <line x1="3.5" y1="20.5" x2="10" y2="14" />
    </svg>
  )
}

export function UserIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <circle cx="12" cy="8" r="3.8" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </svg>
  )
}

export function HashIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <line x1="4" y1="9" x2="20" y2="9" />
      <line x1="4" y1="15" x2="20" y2="15" />
      <line x1="10" y1="4" x2="8" y2="20" />
      <line x1="16" y1="4" x2="14" y2="20" />
    </svg>
  )
}

export function PlusIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...base} {...props}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}
