import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

function getApproved(formData: FormData) {
  return String(formData.get('approved') ?? 'true') !== 'false'
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const key = request.nextUrl.searchParams.get('ADMIN_KEY')
  if (!key || key !== process.env.ADMIN_KEY) {
    return NextResponse.json({ message: 'Unauthorized' }, { status: 403 })
  }

  const formData = await request.formData()
  const approved = getApproved(formData)

  if (approved) {
    await prisma.post.update({ where: { id: Number(id) }, data: { isApproved: true } })
  } else {
    await prisma.post.delete({ where: { id: Number(id) } })
  }

  return NextResponse.redirect(new URL(`/admin?ADMIN_KEY=${key}`, request.url))
}
