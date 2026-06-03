import './globals.css'
import TelegramProvider from '@/components/TelegramProvider'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <TelegramProvider>
          <main className="mx-auto min-h-screen max-w-md px-4 pb-20 pt-4">{children}</main>
        </TelegramProvider>
      </body>
    </html>
  )
}
