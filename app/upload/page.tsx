'use client'

import { motion } from 'framer-motion'
import { Navbar } from '@/components/Navbar'
import { Button } from '@/components/ui/button'
import { MessageSquare, Image, CheckCircle, Sparkles, Compass } from 'lucide-react'

const steps = [
  {
    num: '01',
    title: '开启向导契约',
    desc: '在 Bot 中发送 /desc 指令，唤醒智能投稿向导。',
    icon: MessageSquare,
    color: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  },
  {
    num: '02',
    title: '传送灵魄介质',
    desc: '按照 Bot 提示发送您的精美图片或原创短视频。',
    icon: Image,
    color: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  },
  {
    num: '03',
    title: '填写文案与确认',
    desc: '输入你想对大家说的话，并输入“确认”完成链上发布。',
    icon: CheckCircle,
    color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  },
]

export default function UploadPage() {
  return (
    <div className="space-y-6 pb-24">
      {/* Page Header */}
      <div className="flex items-center gap-2 px-1">
        <div className="p-2 rounded-2xl bg-tgAccent/10 text-tgAccent">
          <Compass size={18} />
        </div>
        <h1 className="text-lg font-bold text-white tracking-wide">智能投稿枢纽</h1>
      </div>

      {/* Guide Banner */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card rounded-3xl p-5 relative overflow-hidden shadow-xl shadow-black/10 border-tgAccent/20 bg-gradient-to-br from-tgBg via-tgBg to-tgAccent/5"
      >
        <div className="absolute -right-6 -bottom-6 h-20 w-20 bg-tgAccent/10 rounded-full blur-xl" />
        <div className="flex items-start gap-3">
          <div className="mt-0.5 p-1 rounded bg-tgAccent/10 text-tgAccent">
            <Sparkles size={14} />
          </div>
          <div className="space-y-1">
            <h2 className="text-sm font-bold text-white tracking-tight">星光璀璨，共创未来</h2>
            <p className="text-[11px] text-white/50 leading-relaxed font-medium">
              所有的投稿内容均通过官方 Telegram 机器人安全投递。成功发布后，您将获得额外的**声望修行值（+15）**！
            </p>
          </div>
        </div>
      </motion.div>

      {/* Vertical Progressive Steps Flow */}
      <div className="space-y-4">
        {steps.map((step, idx) => {
          const Icon = step.icon
          return (
            <motion.div
              key={step.num}
              initial={{ opacity: 0, x: -15 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="flex gap-4 relative"
            >
              {/* Connecting line between steps */}
              {idx < steps.length - 1 && (
                <div className="absolute left-[21px] top-11 bottom-[-20px] w-[2px] bg-gradient-to-b from-tgAccent/20 to-white/5" />
              )}

              {/* Icon / Number Indicator */}
              <div className={`h-11 w-11 shrink-0 rounded-2xl flex items-center justify-center border transition-all ${step.color} shadow-lg shadow-black/5`}>
                <Icon size={18} />
              </div>

              {/* Content Card */}
              <div className="glass-card rounded-2xl p-4 flex-1 space-y-1">
                <div className="flex justify-between items-center">
                  <h3 className="text-xs font-bold text-white">{step.title}</h3>
                  <span className="text-[10px] font-black text-white/10 tracking-widest">{step.num}</span>
                </div>
                <p className="text-[11px] text-white/50 leading-relaxed font-medium">{step.desc}</p>
              </div>
            </motion.div>
          )
        })}
      </div>

      {/* Interactive Main Button */}
      <motion.div
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        className="pt-2"
      >
        <Button
          onClick={() =>
            window.Telegram?.WebApp?.openTelegramLink(
              `https://t.me/${process.env.NEXT_PUBLIC_BOT_USERNAME ?? ''}`
            )
          }
          className="w-full py-6 rounded-2xl bg-gradient-to-r from-blue-500 to-tgAccent text-white font-bold text-sm tracking-wide shadow-lg shadow-blue-500/25 transition-all hover:opacity-95"
        >
          立即前往 Bot 开启投稿
        </Button>
      </motion.div>

      <Navbar />
    </div>
  )
}

