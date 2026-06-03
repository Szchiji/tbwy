interface TelegramWebApp {
  initData: string
  themeParams: {
    accent_color?: string
    bg_color?: string
    text_color?: string
  }
  ready: () => void
  MainButton?: {
    setText: (text: string) => void
    show: () => void
    hide: () => void
    onClick: (cb: () => void) => void
    offClick: (cb: () => void) => void
  }
  HapticFeedback?: {
    impactOccurred: (type: 'light' | 'medium' | 'heavy') => void
  }
  openTelegramLink: (url: string) => void
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp
    }
  }
}

export {}
