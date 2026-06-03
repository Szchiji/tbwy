import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const key = request.nextUrl.searchParams.get('ADMIN_KEY')
  if (!key || key !== process.env.ADMIN_KEY) {
    return NextResponse.json({ message: 'Unauthorized' }, { status: 403 })
  }

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
