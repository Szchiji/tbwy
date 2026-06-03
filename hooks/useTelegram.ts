'use client'

import { useContext } from 'react'
import { TelegramContext } from '@/components/TelegramProvider'

export function useTelegram() {
  return useContext(TelegramContext)
}
