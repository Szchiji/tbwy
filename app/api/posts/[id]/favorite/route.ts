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

  await prisma.favorite.upsert({
    where: { userId_postId: { userId: body.userId, postId: Number(id) } },
    update: {},
    create: { userId: body.userId, postId: Number(id) },
  })

  return NextResponse.json({ status: 'ok', favorited: true })
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = (await request.json()) as { userId?: string; initData?: string }

  if (!body.userId) return NextResponse.json({ message: 'userId required' }, { status: 400 })
  if (!verifyTelegramInitData(body.initData ?? '')) {
    return NextResponse.json({ message: 'Invalid signature' }, { status: 403 })
  }

  await prisma.favorite.deleteMany({
    where: {
      userId: body.userId,
      postId: Number(id),
    },
  })

  return NextResponse.json({ status: 'ok', favorited: false })
}
