import { NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { verifyTelegramInitData } from '@/lib/auth'

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = (await request.json()) as { userId?: string; initData?: string }

  if (!body.userId) return NextResponse.json({ message: 'userId required' }, { status: 400 })
  if (!verifyTelegramInitData(body.initData ?? '')) {
    return NextResponse.json({ message: 'Invalid signature' }, { status: 403 })
  }

  await prisma.userBlacklist.upsert({
    where: { userId_postId: { userId: body.userId, postId: Number(id) } },
    update: {},
    create: { userId: body.userId, postId: Number(id) },
  })

  await prisma.post.update({
    where: { id: Number(id) },
    data: { blacklistCount: { increment: 1 } },
  })

  return NextResponse.json({ status: 'ok' })
}
