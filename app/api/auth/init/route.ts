import { NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { parseTelegramUser, signJWT, verifyTelegramInitData } from '@/lib/auth'

export async function POST(request: Request) {
  const body = (await request.json()) as { initData?: string }
  const initData = body.initData ?? ''

  if (!verifyTelegramInitData(initData)) {
    return NextResponse.json({ message: 'Invalid initData' }, { status: 403 })
  }

  const tgUser = parseTelegramUser(initData)
  if (!tgUser) {
    return NextResponse.json({ message: 'No Telegram user' }, { status: 400 })
  }

  const user = await prisma.user.upsert({
    where: { tgId: String(tgUser.id) },
    update: {
      username: tgUser.username,
      firstName: tgUser.first_name,
      lastName: tgUser.last_name,
      photoUrl: tgUser.photo_url,
    },
    create: {
      tgId: String(tgUser.id),
      username: tgUser.username,
      firstName: tgUser.first_name,
      lastName: tgUser.last_name,
      photoUrl: tgUser.photo_url,
    },
  })

  const token = await signJWT({ sub: user.id, role: user.role, tgId: user.tgId })

  return NextResponse.json({ status: 'ok', token, userId: user.id, user })
}
