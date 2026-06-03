import { NextResponse } from 'next/server'
import { getTelegramBot } from '@/lib/telegram-bot'

export async function POST(request: Request) {
  const bot = getTelegramBot()
  if (!bot) {
    return NextResponse.json({ message: 'Bot not configured' }, { status: 500 })
  }
  const update = await request.json()
  await bot.handleUpdate(update)
  return NextResponse.json({ status: 'ok' })
}
