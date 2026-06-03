import type { ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Button({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        'rounded-xl bg-tgAccent px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
