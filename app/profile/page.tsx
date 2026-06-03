'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Navbar } from '@/components/Navbar'
import { Card } from '@/components/ui/card'
import { useTelegram } from '@/hooks/useTelegram'
import { Sparkles, Award, ShieldCheck, Heart, FileText, ArrowRight, Star, TrendingUp } from 'lucide-react'
import Link from 'next/link'

type UserData = {
  id: string
  tgId: string
  username: string | null
  firstName: string | null
  lastName: string | null
  photoUrl: string | null
  role: string
  creditScore: number
}

export default function ProfilePage() {
  const { userId, initData } = useTelegram()
  const [user, setUser] = useState<UserData | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (!initData) {
      setIsLoading(false)
      return
    }

    fetch('/api/auth/init', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initData }),
    })
      .then((res) => res.json())
      .then((json: { user?: UserData }) => {
        if (json.user) {
          setUser(json.user)
        }
      })
      .catch((e) => console.error(e))
      .finally(() => setIsLoading(false))
  }, [initData])

  // Get tier level based on credit score
  const getCreditTier = (score: number) => {
    if (score >= 150) return { title: '太虚仙尊 👑', color: 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10' }
    if (score >= 120) return { title: '大乘散仙 🌟', color: 'text-purple-400 border-purple-500/30 bg-purple-500/10' }
    if (score >= 100) return { title: '结丹真人 ✨', color: 'text-blue-400 border-blue-500/30 bg-blue-500/10' }
    return { title: '筑基凡人 🍂', color: 'text-white/60 border-white/10 bg-white/[0.02]' }
  }

  const score = user?.creditScore ?? 100
  const tier = getCreditTier(score)
  const displayName = user?.firstName
    ? `${user.firstName}${user.lastName ? ' ' + user.lastName : ''}`
    : user?.username ?? '神秘探索者'

  return (
    <div className="space-y-5 pb-24">
      {/* Page Title */}
      <div className="flex items-center justify-between px-1">
        <h1 className="text-lg font-bold text-white tracking-wide">星光神殿</h1>
        <span className="flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-bold">
          <ShieldCheck size={11} />
          Telegram 密连
        </span>
      </div>

      {isLoading ? (
        <div className="flex py-20 flex-col items-center justify-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-3 border-tgAccent border-t-transparent" />
          <span className="text-xs text-white/50">同步灵魂契约中...</span>
        </div>
      ) : (
        <>
          {/* User Profile Info Card */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass-card rounded-3xl p-5 relative overflow-hidden shadow-xl shadow-black/10"
          >
            <div className="absolute top-0 right-0 -mr-6 -mt-6 h-24 w-24 rounded-full bg-tgAccent/5 blur-xl" />

            <div className="flex items-center gap-4">
              {/* Profile Avatar */}
              {user?.photoUrl ? (
                <div className="relative h-14 w-14 overflow-hidden rounded-2xl border border-white/20">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={user.photoUrl} alt="avatar" className="h-full w-full object-cover" />
                </div>
              ) : (
                <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-blue-500 to-tgAccent p-[1px] shadow-lg shadow-blue-500/20">
                  <div className="h-full w-full rounded-[15px] bg-[#0b0f19] flex items-center justify-center text-lg font-bold text-white">
                    {displayName.slice(0, 1).toUpperCase()}
                  </div>
                </div>
              )}

              <div className="space-y-1">
                <div className="flex items-center gap-1.5">
                  <h2 className="text-base font-bold text-white tracking-tight">{displayName}</h2>
                  <span className="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-tgAccent/10 border border-tgAccent/20 text-tgAccent">
                    {user?.role ?? 'USER'}
                  </span>
                </div>
                <p className="text-[11px] text-white/40 font-medium">UID: {user?.id ?? userId}</p>
              </div>
            </div>
          </motion.div>

          {/* Gamified Reputation / Tier Section */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card rounded-3xl p-5 space-y-4 shadow-xl shadow-black/10"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-white/50 tracking-wider uppercase">声望品级系统</h3>
              <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border transition-all ${tier.color}`}>
                {tier.title}
              </span>
            </div>

            {/* Score Linear Indicator */}
            <div className="space-y-2">
              <div className="flex justify-between items-end text-xs">
                <span className="text-white/80 font-semibold flex items-center gap-1">
                  <Award size={13} className="text-tgAccent" />
                  <span>星光修行值</span>
                </span>
                <span className="text-white font-bold text-sm">
                  {score} <span className="text-white/30 text-[10px]">/ 200</span>
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-white/[0.04] overflow-hidden p-[1px] border border-white/[0.05]">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(100, (score / 200) * 100)}%` }}
                  transition={{ duration: 1, ease: 'easeOut' }}
                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-tgAccent"
                />
              </div>
            </div>

            {/* Reputation Description */}
            <div className="rounded-2xl bg-white/[0.01] border border-white/[0.04] p-3 text-[11px] text-white/50 leading-relaxed">
              您的星光等级决定了您在整个生态中的特权与审核响应速度。通过定期**优质投稿**或**点赞点藏**均能使声望稳步成长。
            </div>
          </motion.div>

          {/* Quick Dash Stats */}
          <div className="grid grid-cols-2 gap-3">
            <Link href="/favorites">
              <motion.div
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="glass-card rounded-3xl p-4 flex items-center gap-3 border border-white/[0.06] hover:border-white/[0.12] transition-all cursor-pointer"
              >
                <div className="p-2.5 rounded-2xl bg-pink-500/10 border border-pink-500/20 text-pink-400">
                  <Heart size={16} className="fill-pink-500/10" />
                </div>
                <div>
                  <h4 className="text-[10px] font-semibold text-white/40 tracking-wider">我的收藏</h4>
                  <span className="text-sm font-bold text-white flex items-center gap-1 mt-0.5">
                    查看全部 <ArrowRight size={11} />
                  </span>
                </div>
              </motion.div>
            </Link>

            <Link href="/upload">
              <motion.div
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="glass-card rounded-3xl p-4 flex items-center gap-3 border border-white/[0.06] hover:border-white/[0.12] transition-all cursor-pointer"
              >
                <div className="p-2.5 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
                  <FileText size={16} />
                </div>
                <div>
                  <h4 className="text-[10px] font-semibold text-white/40 tracking-wider">快速投稿</h4>
                  <span className="text-sm font-bold text-white flex items-center gap-1 mt-0.5">
                    进入向导 <ArrowRight size={11} />
                  </span>
                </div>
              </motion.div>
            </Link>
          </div>

          {/* Achievements badge showcase */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-card rounded-3xl p-5 space-y-3.5 shadow-xl shadow-black/10"
          >
            <h3 className="text-xs font-bold text-white/50 tracking-wider uppercase">我的勋章</h3>
            <div className="flex gap-4">
              <div className="flex flex-col items-center gap-1">
                <div className="h-10 w-10 rounded-full bg-tgAccent/10 border border-tgAccent/20 flex items-center justify-center text-tgAccent">
                  <Star size={18} className="fill-tgAccent/10" />
                </div>
                <span className="text-[9px] font-bold text-white/60">初露锋芒</span>
              </div>
              <div className="flex flex-col items-center gap-1 opacity-30">
                <div className="h-10 w-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white">
                  <TrendingUp size={18} />
                </div>
                <span className="text-[9px] font-bold text-white/40">百赞元老</span>
              </div>
              <div className="flex flex-col items-center gap-1 opacity-30">
                <div className="h-10 w-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white">
                  <Sparkles size={18} />
                </div>
                <span className="text-[9px] font-bold text-white/40">创作大师</span>
              </div>
            </div>
          </motion.div>
        </>
      )}

      <Navbar />
    </div>
  )
}

