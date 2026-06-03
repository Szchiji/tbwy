import { NextResponse } from 'next/server'
import { getTelegramBot } from '@/lib/telegram-bot'

export async function POST(request: Request) {
  try {
    const bot = getTelegramBot()
    if (!bot) {
      console.error('Telegram Bot is not configured (missing TELEGRAM_BOT_TOKEN)')
      return NextResponse.json({ message: 'Bot not configured' }, { status: 500 })
    }
    const update = await request.json()
    await bot.handleUpdate(update)
    return NextResponse.json({ status: 'ok' })
  } catch (error: any) {
    console.error('Error handling Telegram webhook update:', error)
    // Return 200 OK with error payload to prevent Telegram webhook endless retry storm on failures
    return NextResponse.json({ status: 'error', error: error.message }, { status: 200 })
  }
}

export async function GET() {
  try {
    const bot = getTelegramBot()
    if (!bot) {
      return NextResponse.json({ message: 'Bot not configured' }, { status: 500 })
    }
    const baseUrl = process.env.BASE_URL
    if (!baseUrl) {
      return NextResponse.json({ message: 'BASE_URL not configured' }, { status: 400 })
    }
    const webhookUrl = `${baseUrl}/api/webhook`
    await bot.api.setWebhook(webhookUrl)
    return NextResponse.json({ message: 'Webhook set successfully', url: webhookUrl })
  } catch (error: any) {
    console.error('Error setting webhook:', error)
    return NextResponse.json({ message: 'Failed to set webhook', error: error.message }, { status: 500 })
  }
}
