import { NextRequest, NextResponse } from 'next/server'
import { prisma } from '@/lib/prisma'

function isAuthorized(request: NextRequest) {
  const key = request.nextUrl.searchParams.get('ADMIN_KEY')
  return Boolean(key && key === process.env.ADMIN_KEY)
}

export async function GET(request: NextRequest) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ message: 'Unauthorized' }, { status: 403 })
  }
  const settings = await prisma.setting.findMany({ orderBy: { key: 'asc' } })
  return NextResponse.json(settings)
}

export async function PUT(request: NextRequest) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ message: 'Unauthorized' }, { status: 403 })
  }
  const body = (await request.json()) as { key?: string; value?: string }
  if (!body.key) return NextResponse.json({ message: 'key required' }, { status: 400 })

  const setting = await prisma.setting.upsert({
    where: { key: body.key },
    update: { value: body.value ?? '' },
    create: { key: body.key, value: body.value ?? '' },
  })

  return NextResponse.json(setting)
}

export async function POST(request: NextRequest) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ message: 'Unauthorized' }, { status: 403 })
  }
  const formData = await request.formData()
  const key = String(formData.get('key') ?? '')
  const value = String(formData.get('value') ?? '')
  if (!key) return NextResponse.json({ message: 'key required' }, { status: 400 })

  await prisma.setting.upsert({
    where: { key },
    update: { value },
    create: { key, value },
  })

  return NextResponse.redirect(new URL(`/admin?ADMIN_KEY=${request.nextUrl.searchParams.get('ADMIN_KEY') ?? ''}`, request.url))
}
