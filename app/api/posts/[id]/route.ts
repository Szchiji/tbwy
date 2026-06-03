import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const postId = Number(id)
  if (!Number.isFinite(postId)) return NextResponse.json({ message: 'Invalid id' }, { status: 400 })

  const post = await prisma.post.findUnique({
    where: { id: postId },
    include: {
      comments: { orderBy: { createdAt: 'desc' }, take: 50 },
    },
  })

  if (!post) return NextResponse.json({ message: 'Not found' }, { status: 404 })

  const siblings = post.mediaGroupId
    ? await prisma.post.findMany({
        where: { mediaGroupId: post.mediaGroupId, isApproved: true },
        orderBy: { id: 'asc' },
      })
    : [post]

  return NextResponse.json({
    id: post.id,
    title: post.title,
    text: post.text,
    likes: post.likes,
    media: siblings
      .map((item) => ({ id: item.id, src: item.firstMedia }))
      .filter((item): item is { id: number; src: string } => Boolean(item.src)),
    comments: post.comments.map((comment) => ({
      id: comment.id,
      content: comment.content,
      createdAt: comment.createdAt.toISOString(),
    })),
  })
}

export async function DELETE(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  await prisma.post.delete({ where: { id: Number(id) } })
  return NextResponse.json({ status: 'ok' })
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const key = request.nextUrl.searchParams.get('ADMIN_KEY')
  if (!key || key !== process.env.ADMIN_KEY) {
    return NextResponse.json({ message: 'Unauthorized' }, { status: 403 })
  }
  await prisma.post.delete({ where: { id: Number(id) } })
  return NextResponse.redirect(new URL(`/admin?ADMIN_KEY=${key}`, request.url))
}
