'use client'

import { useEffect } from 'react'

type Props = {
  text: string
  onClick: () => void
}

export function MainButton({ text, onClick }: Props) {
  useEffect(() => {
    const button = window.Telegram?.WebApp?.MainButton
    if (!button) return
    button.setText(text)
    button.show()
    button.onClick(onClick)
    return () => {
      button.offClick(onClick)
      button.hide()
    }
  }, [onClick, text])

  return null
}
