'use client'

import { Navbar } from '@/components/Navbar'
import { Button } from '@/components/ui/button'

export default function UploadPage() {
  return (
    <>
      <h1 className="mb-3 text-lg font-semibold">投稿引导</h1>
      <p className="mb-4 text-sm text-white/80">在 Bot 内发送 /desc 后，按引导完成投稿流程。</p>
      <Button onClick={() => window.Telegram?.WebApp?.openTelegramLink(`https://t.me/${process.env.NEXT_PUBLIC_BOT_USERNAME ?? ''}`)}>打开 Bot 投稿</Button>
      <Navbar />
    </>
  )
}
