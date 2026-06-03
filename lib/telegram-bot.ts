import { Bot } from 'grammy'
import { prisma } from '@/lib/prisma'

const token = process.env.TELEGRAM_BOT_TOKEN
let botRef: Bot | null = null
let initialized = false

type StateData = {
  media?: string
  description?: string
}

function getFromId(ctx: { from?: { id: number } }) {
  return ctx.from ? String(ctx.from.id) : null
}

async function getState(userId: string) {
  return prisma.botState.findUnique({ where: { userId } })
}

async function setState(userId: string, state: string, data: StateData = {}) {
  await prisma.botState.upsert({
    where: { userId },
    update: { state, data },
    create: { userId, state, data },
  })
}

export function getTelegramBot() {
  if (!token) return null
  if (!botRef) {
    botRef = new Bot(token)
  }
  if (initialized) return botRef

  botRef.command('start', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    await setState(fromId, 'idle', {})
    await ctx.reply('欢迎使用 Mini App，发送 /desc 开始投稿。')
  })

  botRef.command('cancel', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    await setState(fromId, 'idle', {})
    await ctx.reply('已取消当前流程。')
  })

  botRef.command('notice', async (ctx) => {
    await ctx.reply('公告请在管理后台设置。')
  })

  botRef.command('sync', async (ctx) => {
    await ctx.reply('同步完成。')
  })

  botRef.command('admin', async (ctx) => {
    await ctx.reply('请通过管理后台处理审核。')
  })

  botRef.command('desc', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    await setState(fromId, 'waiting_media', {})
    await ctx.reply('请发送图片或视频。')
  })

  botRef.on('message', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    const userId = fromId
    const current = await getState(userId)
    const state = current?.state ?? 'idle'
    const data = (current?.data ?? {}) as StateData

    if (state === 'waiting_media') {
      const photo = ctx.message.photo?.at(-1)
      const video = ctx.message.video
      const fileId = photo?.file_id ?? video?.file_id
      if (!fileId) {
        await ctx.reply('请发送有效图片或视频。')
        return
      }
      await setState(userId, 'waiting_description', { media: fileId })
      await ctx.reply('请发送描述文本。')
      return
    }

    if (state === 'waiting_description' && ctx.message.text) {
      await setState(userId, 'waiting_confirm', { ...data, description: ctx.message.text })
      await ctx.reply('确认投稿请回复: 确认')
      return
    }

    if (state === 'waiting_confirm' && ctx.message.text === '确认') {
      const created = await prisma.post.create({
        data: {
          text: data.description,
          title: data.description?.slice(0, 40),
          firstMedia: data.media,
          isApproved: false,
          customDescription: data.description,
        },
      })
      await setState(userId, 'idle', {})
      await ctx.reply(`投稿已提交，编号 ${created.id}，等待审核。`)
      const adminChatId = process.env.MY_CHAT_ID
      if (adminChatId) {
        await ctx.api.sendMessage(adminChatId, `新投稿待审核：${created.id}`)
      }
      return
    }
  })

  botRef.on('callback_query:data', async (ctx) => {
    const data = ctx.callbackQuery.data
    if (!data) return
    if (data.startsWith('y_')) {
      const id = Number(data.slice(2))
      if (Number.isFinite(id)) {
        await prisma.post.update({ where: { id }, data: { isApproved: true } })
      }
      await ctx.answerCallbackQuery({ text: '已通过' })
    }
    if (data.startsWith('n_')) {
      const id = Number(data.slice(2))
      if (Number.isFinite(id)) {
        await prisma.post.delete({ where: { id } }).catch(() => null)
      }
      await ctx.answerCallbackQuery({ text: '已拒绝' })
    }
  })

  initialized = true
  return botRef
}
