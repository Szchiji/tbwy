import { NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'
import { verifyTelegramInitData } from '@/lib/auth'

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = (await request.json()) as { content?: string; initData?: string; userId?: string }

  if (!verifyTelegramInitData(body.initData ?? '')) {
    return NextResponse.json({ message: 'Invalid signature' }, { status: 403 })
  }

  if (!body.content?.trim()) {
    return NextResponse.json({ message: 'content required' }, { status: 400 })
  }

  const comment = await prisma.comment.create({
    data: {
      postId: Number(id),
      content: body.content.trim(),
      authorId: body.userId,
    },
  })

  return NextResponse.json({
    id: comment.id,
    content: comment.content,
    createdAt: comment.createdAt.toISOString(),
  })
}
