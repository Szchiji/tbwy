import type { Config } from 'tailwindcss'

export default {
  darkMode: ['class'],
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        tgAccent: 'var(--tg-accent, #a78bfa)',
        tgBg: 'var(--tg-bg, #0b0f19)',
        tgText: 'var(--tg-text, #f8fafc)',
      },
    },
  },
  plugins: [],
} satisfies Config
