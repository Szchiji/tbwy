'use client'

import { createContext, useEffect, useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

type TelegramCtx = {
  initData: string
  userId: string
  haptic: (type?: 'light' | 'medium' | 'heavy') => void
}

export const TelegramContext = createContext<TelegramCtx>({
  initData: '',
  userId: 'anonymous',
  haptic: () => undefined,
})

export default function TelegramProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient())
  const [initData, setInitData] = useState('')
  const [userId, setUserId] = useState('anonymous')

  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (!tg) return
    tg.ready()
    const accent = tg.themeParams.accent_color ?? '#a78bfa'
    const bg = tg.themeParams.bg_color ?? '#0b0f19'
    const text = tg.themeParams.text_color ?? '#f8fafc'
    document.documentElement.style.setProperty('--tg-accent', accent)
    document.documentElement.style.setProperty('--tg-bg', bg)
    document.documentElement.style.setProperty('--tg-text', text)

    setInitData(tg.initData)

    fetch('/api/auth/init', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initData: tg.initData }),
    })
      .then((res) => res.json())
      .then((json: { userId?: string }) => setUserId(json.userId ?? 'anonymous'))
      .catch(() => undefined)
  }, [])

  const value = useMemo<TelegramCtx>(
    () => ({
      initData,
      userId,
      haptic: (type = 'light') => {
        window.Telegram?.WebApp?.HapticFeedback?.impactOccurred(type)
      },
    }),
    [initData, userId],
  )

  return (
    <QueryClientProvider client={queryClient}>
      <TelegramContext.Provider value={value}>{children}</TelegramContext.Provider>
    </QueryClientProvider>
  )
}
