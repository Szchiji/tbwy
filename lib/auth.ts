import crypto from 'node:crypto'
import { jwtVerify, SignJWT } from 'jose'

type JwtPayload = {
  sub: string
  role: string
  tgId: string
}

const textEncoder = new TextEncoder()

function getJwtSecret() {
  const secret = process.env.NEXTAUTH_SECRET
  if (!secret) {
    throw new Error('NEXTAUTH_SECRET is required')
  }
  return textEncoder.encode(secret)
}

export function verifyTelegramInitData(initData: string): boolean {
  const token = process.env.TELEGRAM_BOT_TOKEN
  if (!token || !initData) return false

  const searchParams = new URLSearchParams(initData)
  const receivedHash = searchParams.get('hash')
  if (!receivedHash) return false

  searchParams.delete('hash')
  const dataCheckString = [...searchParams.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${value}`)
    .join('\n')

  const secretKey = crypto.createHmac('sha256', 'WebAppData').update(token).digest()
  const calculatedHash = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex')

  if (calculatedHash.length !== receivedHash.length) return false
  return crypto.timingSafeEqual(Buffer.from(calculatedHash), Buffer.from(receivedHash))
}

export async function signJWT(payload: JwtPayload): Promise<string> {
  return new SignJWT(payload)
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('7d')
    .sign(getJwtSecret())
}

export async function verifyJWT(token: string): Promise<JwtPayload> {
  const { payload } = await jwtVerify(token, getJwtSecret())
  if (typeof payload.sub !== 'string' || typeof payload.role !== 'string' || typeof payload.tgId !== 'string') {
    throw new Error('Invalid JWT payload')
  }
  return {
    sub: payload.sub,
    role: payload.role,
    tgId: payload.tgId,
  }
}

export function parseTelegramUser(initData: string) {
  const data = new URLSearchParams(initData)
  const userText = data.get('user')
  if (!userText) return null
  const user = JSON.parse(userText) as Partial<{
    id: number
    username: string
    first_name: string
    last_name: string
    photo_url: string
  }>
  if (typeof user.id !== 'number') return null
  return user
}
