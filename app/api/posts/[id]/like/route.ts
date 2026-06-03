import { NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const postId = Number(id)

  const post = await prisma.post.update({
    where: { id: postId },
    data: { likes: { increment: 1 } },
  })

  return NextResponse.json({ status: 'ok', likes: post.likes })
}
