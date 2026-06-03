import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

const PAGE_SIZE = 20

export async function GET(request: NextRequest) {
  const cursor = request.nextUrl.searchParams.get('cursor')
  const search = request.nextUrl.searchParams.get('search') ?? ''
  const type = request.nextUrl.searchParams.get('type') ?? 'all'
  const sort = request.nextUrl.searchParams.get('sort') ?? 'latest'
  const tag = request.nextUrl.searchParams.get('tag') ?? ''
  const favoritesOf = request.nextUrl.searchParams.get('favoritesOf')

  const whereBase = {
    isApproved: true,
    ...(search
      ? {
          OR: [
            { title: { contains: search, mode: 'insensitive' as const } },
            { text: { contains: search, mode: 'insensitive' as const } },
          ],
        }
      : {}),
    ...(type === 'image' ? { firstMedia: { startsWith: 'AgAC' } } : {}),
    ...(type === 'video' ? { firstMedia: { startsWith: 'BAAC' } } : {}),
    ...(tag ? { tags: { contains: tag, mode: 'insensitive' as const } } : {}),
    ...(favoritesOf ? { favorites: { some: { userId: favoritesOf } } } : {}),
  }

  const posts = await prisma.post.findMany({
    where: whereBase,
    orderBy: sort === 'hot' ? [{ likes: 'desc' }, { date: 'desc' }] : [{ date: 'desc' }],
    take: PAGE_SIZE + 1,
    ...(cursor ? { cursor: { id: Number(cursor) }, skip: 1 } : {}),
    include: { _count: { select: { comments: true } } },
  })

  const hasMore = posts.length > PAGE_SIZE
  const items = posts.slice(0, PAGE_SIZE)

  return NextResponse.json({
    items: items.map((post) => ({
      id: post.id,
      title: post.title,
      text: post.text,
      likes: post.likes,
      date: post.date.toISOString(),
      firstMedia: post.firstMedia,
      thumbnail: post.thumbnail,
      mediaGroupId: post.mediaGroupId,
      tags: post.tags,
      commentsCount: post._count.comments,
    })),
    nextCursor: hasMore ? String(items[items.length - 1]?.id ?? '') : null,
  })
}

export async function POST(request: Request) {
  const body = (await request.json()) as {
    title?: string
    text?: string
    firstMedia?: string
    mediaGroupId?: string
    tags?: string
    authorId?: string
  }

  const post = await prisma.post.create({
    data: {
      title: body.title,
      text: body.text,
      firstMedia: body.firstMedia,
      mediaGroupId: body.mediaGroupId,
      tags: body.tags ?? '',
      authorId: body.authorId,
      isApproved: false,
    },
  })

  return NextResponse.json(post)
}
