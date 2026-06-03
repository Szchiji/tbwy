import { Bot } from 'grammy'
import { prisma } from '@/lib/prisma'

const token = process.env.TELEGRAM_BOT_TOKEN
let botRef: Bot | null = null
let initialized = false

type StateData = {
  media?: string
  mediaType?: 'photo' | 'video'
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
    botRef.catch((err) => {
      console.error('Error in Grammy bot handler:', err.error)
    })
  }
  if (initialized) return botRef

  botRef.command('start', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    await setState(fromId, 'idle', {})
    
    const replyMarkup = {
      inline_keyboard: [
        [
          { text: '🚀 进入小程序', web_app: { url: process.env.BASE_URL || '' } }
        ],
        [
          { text: '📝 发起快捷投稿', callback_data: 'flow_start_desc' }
        ]
      ]
    }
    
    await ctx.reply('👋 欢迎使用智能投稿与内容共创 Mini App！\n\n您可以直接点击下方按钮进入小程序浏览精彩内容，或发起快捷投稿：', {
      reply_markup: replyMarkup
    })
  })

  botRef.command('cancel', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    await setState(fromId, 'idle', {})
    await ctx.reply('❌ 已取消当前投稿流程。')
  })

  botRef.command('notice', async (ctx) => {
    try {
      const noticeSetting = await prisma.setting.findUnique({ where: { key: 'notice' } })
      if (noticeSetting?.value) {
        await ctx.reply(`📢 最新公告：\n\n${noticeSetting.value}`)
      } else {
        await ctx.reply('📢 暂无最新公告。请在管理后台中进行设置。')
      }
    } catch (e) {
      console.error(e)
      await ctx.reply('📢 暂无最新公告。')
    }
  })

  botRef.command('sync', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    try {
      const user = await prisma.user.findUnique({
        where: { tgId: fromId },
        include: {
          _count: {
            select: { posts: true, comments: true, favorites: true }
          }
        }
      })
      if (!user) {
        await ctx.reply('🔍 暂未在小程序中建立您的契约档案，请点击下方按钮开启小程序，系统将自动为您注册。', {
          reply_markup: {
            inline_keyboard: [
              [
                { text: '🚀 进入小程序注册', web_app: { url: process.env.BASE_URL || '' } }
              ]
            ]
          }
        })
      } else {
        await ctx.reply(`👤 契约者档案：\n\n👤 昵称：${user.firstName || ''} ${user.lastName || ''}\n🌟 声望修行值：${user.creditScore}\n📝 已投稿数：${user._count.posts}\n💬 评论次数：${user._count.comments}\n💖 收藏内容：${user._count.favorites}\n\n数据已与小程序无缝安全同步。`)
      }
    } catch (e) {
      console.error(e)
      await ctx.reply('🔄 同步完成。')
    }
  })

  botRef.command('admin', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    const isAdminChat = String(fromId) === process.env.MY_CHAT_ID
    
    let userAdmin = false
    try {
      const user = await prisma.user.findUnique({ where: { tgId: fromId } })
      if (user?.role === 'ADMIN' || user?.role === 'MODERATOR') {
        userAdmin = true
      }
    } catch (e) {
      console.error(e)
    }

    if (isAdminChat || userAdmin) {
      const adminUrl = `${process.env.BASE_URL || ''}/admin?ADMIN_KEY=${process.env.ADMIN_KEY || ''}`
      await ctx.reply('🔐 尊敬的管理员，您可以直接点击下方按钮，在 Telegram 内部无缝安全地打开管理后台面板进行审核与设置。', {
        reply_markup: {
          inline_keyboard: [
            [
              { text: '🛠️ 打开管理后台', web_app: { url: adminUrl } }
            ]
          ]
        }
      })
    } else {
      await ctx.reply('⚠️ 抱歉，您没有权限使用该指令。')
    }
  })

  botRef.command('desc', async (ctx) => {
    const fromId = getFromId(ctx)
    if (!fromId) return
    await setState(fromId, 'waiting_media', {})
    await ctx.reply('📝 快捷投稿启动中...\n\n请发送您要投稿的图片或视频：', {
      reply_markup: {
        inline_keyboard: [
          [{ text: '❌ 取消当前投稿', callback_data: 'flow_cancel' }]
        ]
      }
    })
  })

  botRef.command('help', async (ctx) => {
    await ctx.reply('🤖 智能内容共创机器人指令说明：\n\n' +
      '/start - 启动机器人并开启功能菜单\n' +
      '/desc - 开启图片/视频快捷投稿流程\n' +
      '/cancel - 取消当前的投稿流程\n' +
      '/sync - 查询并同步您的小程序契约者档案\n' +
      '/notice - 查看系统最新公告\n' +
      '/admin - 管理员专用的后台安全管理快捷入口\n' +
      '/help - 查看此帮助信息')
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
        await ctx.reply('⚠️ 请发送有效图片或视频，或者点击下方按钮取消。', {
          reply_markup: {
            inline_keyboard: [
              [{ text: '❌ 取消当前投稿', callback_data: 'flow_cancel' }]
            ]
          }
        })
        return
      }
      const mediaType = photo ? 'photo' : 'video'
      await setState(userId, 'waiting_description', { media: fileId, mediaType })
      await ctx.reply('✍️ 媒体接收成功！请发送该投稿的描述文本/文案：', {
        reply_markup: {
          inline_keyboard: [
            [{ text: '❌ 取消当前投稿', callback_data: 'flow_cancel' }]
          ]
        }
      })
      return
    }

    if (state === 'waiting_description') {
      if (ctx.message.text) {
        await setState(userId, 'waiting_confirm', { ...data, description: ctx.message.text })
        await ctx.reply(`🔍 投稿信息核对：\n\n📝 描述：${ctx.message.text}\n\n确认无误后，请点击下方按钮完成投递：`, {
          reply_markup: {
            inline_keyboard: [
              [
                { text: '✅ 确认投稿', callback_data: 'flow_confirm' },
                { text: '❌ 取消', callback_data: 'flow_cancel' }
              ]
            ]
          }
        })
      } else {
        await ctx.reply('⚠️ 请发送该投稿的描述文本/文案，或者点击下方按钮取消。', {
          reply_markup: {
            inline_keyboard: [
              [{ text: '❌ 取消当前投稿', callback_data: 'flow_cancel' }]
            ]
          }
        })
      }
      return
    }

    if (state === 'waiting_confirm') {
      if (ctx.message.text === '确认') {
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
        await ctx.reply(`🎉 投稿已成功提交！\n📝 投稿编号：${created.id}\n\n我们的管理员正在对内容进行审核，请耐心等待。`)
        
        const adminChatId = process.env.MY_CHAT_ID
        if (adminChatId) {
          const caption = `💡 新投稿待审核\n📝 编号：${created.id}\n📝 描述：${created.text || '无'}`
          const replyMarkup = {
            inline_keyboard: [
              [
                { text: '✅ 通过', callback_data: `y_${created.id}` },
                { text: '❌ 拒绝', callback_data: `n_${created.id}` }
              ]
            ]
          }
          if (created.firstMedia) {
            try {
              if (data.mediaType === 'video') {
                await ctx.api.sendVideo(adminChatId, created.firstMedia, { caption, reply_markup: replyMarkup })
              } else {
                await ctx.api.sendPhoto(adminChatId, created.firstMedia, { caption, reply_markup: replyMarkup })
              }
            } catch (e) {
              console.error('Failed to send media to admin, fallback to message', e)
              await ctx.api.sendMessage(adminChatId, caption, { reply_markup: replyMarkup })
            }
          } else {
            await ctx.api.sendMessage(adminChatId, caption, { reply_markup: replyMarkup })
          }
        }
      } else {
        await ctx.reply('⚠️ 确认无误后，请点击下方按钮「确认投稿」完成投递，或者直接回复「确认」进行投稿：', {
          reply_markup: {
            inline_keyboard: [
              [
                { text: '✅ 确认投稿', callback_data: 'flow_confirm' },
                { text: '❌ 取消', callback_data: 'flow_cancel' }
              ]
            ]
          }
        })
      }
      return
    }

    // Default fallback response for text messages in idle state or unhandled states
    if (ctx.message?.text && !ctx.message.text.startsWith('/')) {
      const replyMarkup = {
        inline_keyboard: [
          [
            { text: '🚀 进入小程序', web_app: { url: process.env.BASE_URL || '' } }
          ],
          [
            { text: '📝 发起快捷投稿', callback_data: 'flow_start_desc' }
          ]
        ]
      }
      await ctx.reply('👋 您好！目前没有处于投稿流程中。\n您可以直接点击下方按钮进入小程序浏览精彩内容，或发起快捷投稿：', {
        reply_markup: replyMarkup
      })
    }
  })

  botRef.on('callback_query:data', async (ctx) => {
    const data = ctx.callbackQuery.data
    if (!data) return

    if (data === 'flow_cancel') {
      const fromId = getFromId(ctx)
      if (fromId) {
        await setState(fromId, 'idle', {})
      }
      try {
        await ctx.editMessageText('❌ 已取消当前投稿流程。', { reply_markup: { inline_keyboard: [] } })
      } catch {
        await ctx.editMessageReplyMarkup({ reply_markup: { inline_keyboard: [] } }).catch(() => null)
        await ctx.reply('❌ 已取消当前投稿流程。')
      }
      await ctx.answerCallbackQuery({ text: '流程已取消' })
      return
    }

    if (data === 'flow_start_desc') {
      const fromId = getFromId(ctx)
      if (!fromId) return
      await setState(fromId, 'waiting_media', {})
      try {
        await ctx.editMessageText('📝 快捷投稿启动中...\n\n请发送您要投稿的图片或视频：', {
          reply_markup: {
            inline_keyboard: [
              [{ text: '❌ 取消当前投稿', callback_data: 'flow_cancel' }]
            ]
          }
        })
      } catch {
        await ctx.reply('📝 请发送您要投稿的图片或视频：', {
          reply_markup: {
            inline_keyboard: [
              [{ text: '❌ 取消当前投稿', callback_data: 'flow_cancel' }]
            ]
          }
        })
      }
      await ctx.answerCallbackQuery()
      return
    }

    if (data === 'flow_confirm') {
      const fromId = getFromId(ctx)
      if (!fromId) return
      const current = await getState(fromId)
      const state = current?.state ?? 'idle'
      const stateData = (current?.data ?? {}) as StateData

      if (state === 'waiting_confirm') {
        const created = await prisma.post.create({
          data: {
            text: stateData.description,
            title: stateData.description?.slice(0, 40),
            firstMedia: stateData.media,
            isApproved: false,
            customDescription: stateData.description,
          },
        })
        await setState(fromId, 'idle', {})
        
        try {
          await ctx.editMessageText(`🎉 投稿已成功提交！\n📝 投稿编号：${created.id}\n\n我们的管理员正在对内容进行审核，请耐心等待。`, { reply_markup: { inline_keyboard: [] } })
        } catch {
          await ctx.editMessageReplyMarkup({ reply_markup: { inline_keyboard: [] } }).catch(() => null)
          await ctx.reply(`🎉 投稿已成功提交！\n📝 投稿编号：${created.id}\n\n我们的管理员正在对内容进行审核，请耐心等待。`)
        }
        await ctx.answerCallbackQuery({ text: '投稿成功' })

        const adminChatId = process.env.MY_CHAT_ID
        if (adminChatId) {
          const caption = `💡 新投稿待审核\n📝 编号：${created.id}\n📝 描述：${created.text || '无'}`
          const replyMarkup = {
            inline_keyboard: [
              [
                { text: '✅ 通过', callback_data: `y_${created.id}` },
                { text: '❌ 拒绝', callback_data: `n_${created.id}` }
              ]
            ]
          }
          if (created.firstMedia) {
            try {
              if (stateData.mediaType === 'video') {
                await ctx.api.sendVideo(adminChatId, created.firstMedia, { caption, reply_markup: replyMarkup })
              } else {
                await ctx.api.sendPhoto(adminChatId, created.firstMedia, { caption, reply_markup: replyMarkup })
              }
            } catch (e) {
              console.error('Failed to send media to admin, fallback to message', e)
              await ctx.api.sendMessage(adminChatId, caption, { reply_markup: replyMarkup })
            }
          } else {
            await ctx.api.sendMessage(adminChatId, caption, { reply_markup: replyMarkup })
          }
        }
      } else {
        await ctx.answerCallbackQuery({ text: '当前状态不需要确认' })
      }
      return
    }

    if (data.startsWith('y_')) {
      const id = Number(data.slice(2))
      if (Number.isFinite(id)) {
        await prisma.post.update({ where: { id }, data: { isApproved: true } })
        try {
          const currentText = ctx.callbackQuery.message?.text || ctx.callbackQuery.message?.caption || ''
          const newText = `✅【已通过】\n\n${currentText}`
          if (ctx.callbackQuery.message?.text) {
            await ctx.editMessageText(newText, { reply_markup: { inline_keyboard: [] } })
          } else if (ctx.callbackQuery.message?.caption) {
            await ctx.editMessageCaption({ caption: newText, reply_markup: { inline_keyboard: [] } })
          } else {
            await ctx.editMessageReplyMarkup({ reply_markup: { inline_keyboard: [] } })
          }
        } catch (e) {
          await ctx.editMessageReplyMarkup({ reply_markup: { inline_keyboard: [] } }).catch(() => null)
        }
      }
      await ctx.answerCallbackQuery({ text: '已通过' })
    }

    if (data.startsWith('n_')) {
      const id = Number(data.slice(2))
      if (Number.isFinite(id)) {
        await prisma.post.delete({ where: { id } }).catch(() => null)
        try {
          const currentText = ctx.callbackQuery.message?.text || ctx.callbackQuery.message?.caption || ''
          const newText = `❌【已拒绝并删除】\n\n${currentText}`
          if (ctx.callbackQuery.message?.text) {
            await ctx.editMessageText(newText, { reply_markup: { inline_keyboard: [] } })
          } else if (ctx.callbackQuery.message?.caption) {
            await ctx.editMessageCaption({ caption: newText, reply_markup: { inline_keyboard: [] } })
          } else {
            await ctx.editMessageReplyMarkup({ reply_markup: { inline_keyboard: [] } })
          }
        } catch (e) {
          await ctx.editMessageReplyMarkup({ reply_markup: { inline_keyboard: [] } }).catch(() => null)
        }
      }
      await ctx.answerCallbackQuery({ text: '已拒绝' })
    }
  })

  initialized = true
  return botRef
}
