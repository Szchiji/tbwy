'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { Heart, Bookmark, EyeOff, Send, ArrowLeft, MessageSquare, Sparkles, User, Calendar } from 'lucide-react'
import { MainButton } from '@/components/MainButton'
import { Navbar } from '@/components/Navbar'
import { PostGallery } from '@/components/PostGallery'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useTelegram } from '@/hooks/useTelegram'

type Comment = { id: number; content: string; createdAt: string; authorName?: string }
type Detail = {
  id: number
  title: string | null
  text: string | null
  likes: number
  media: Array<{ id: number; src: string }>
  comments: Comment[]
}

export default function PostDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const [detail, setDetail] = useState<Detail | null>(null)
  const [content, setContent] = useState('')
  const [isLiking, setIsLiking] = useState(false)
  const [isFavoriting, setIsFavoriting] = useState(false)
  const [isBlacklisting, setIsBlacklisting] = useState(false)
  const { userId, initData, haptic } = useTelegram()

  const postId = useMemo(() => Number(params.id), [params.id])

  useEffect(() => {
    fetch(`/api/posts/${postId}`)
      .then((res) => res.json())
      .then((json: Detail) => setDetail(json))
      .catch(() => undefined)
  }, [postId])

  if (!detail) {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-3 border-tgAccent border-t-transparent" />
        <span className="text-xs text-white/50 tracking-wider">智能加载中...</span>
      </div>
    )
  }

  const callAction = async (
    path: string,
    actionType: 'like' | 'favorite' | 'blacklist' | 'comment',
    body: Record<string, string> = {}
  ) => {
    haptic('medium')

    if (actionType === 'like') setIsLiking(true)
    if (actionType === 'favorite') setIsFavoriting(true)
    if (actionType === 'blacklist') setIsBlacklisting(true)

    try {
      await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, initData, ...body }),
      })
      const refreshed = await fetch(`/api/posts/${postId}`).then((r) => r.json() as Promise<Detail>)
      setDetail(refreshed)
    } catch (e) {
      console.error(e)
    } finally {
      setIsLiking(false)
      setIsFavoriting(false)
      setIsBlacklisting(false)
    }
  }

  return (
    <div className="space-y-5 pb-28">
      {/* Top Navigation Row */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.back()}
          className="p-2.5 rounded-full bg-white/[0.03] border border-white/[0.08] text-white/80 hover:text-white transition-all active:scale-95"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="line-clamp-1 text-base font-bold text-white tracking-wide">
            {detail.title ?? '帖子详情'}
          </h1>
        </div>
      </div>

      {/* Post Gallery Carousel */}
      <PostGallery items={detail.media} />

      {/* Post content and body */}
      <div className="glass-card rounded-3xl p-5 space-y-4 shadow-xl shadow-black/10">
        <div className="flex items-center justify-between text-[11px] text-white/40">
          <span className="flex items-center gap-1">
            <User size={12} className="text-tgAccent" />
            <span>发布于系统</span>
          </span>
          <span className="flex items-center gap-1">
            <Calendar size={12} />
            <span>智能加密存证</span>
          </span>
        </div>

        <p className="text-sm text-white/90 leading-relaxed font-medium whitespace-pre-wrap">
          {detail.text}
        </p>

        {/* Premium Interactive Action Ribbon */}
        <div className="pt-2 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {/* Like button */}
            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={() => void callAction(`/api/posts/${postId}/like`, 'like')}
              disabled={isLiking}
              className={`flex items-center gap-1.5 py-2 px-4 rounded-full border text-xs font-semibold transition-all ${
                detail.likes > 0
                  ? 'bg-red-500/10 border-red-500/20 text-red-400'
                  : 'bg-white/[0.03] border-white/[0.08] text-white/70 hover:text-white'
              }`}
            >
              <Heart size={14} className={detail.likes > 0 ? 'fill-red-500/20 stroke-red-400' : 'stroke-white/70'} />
              <span>{detail.likes} 点赞</span>
            </motion.button>

            {/* Favorite Button */}
            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={() => void callAction(`/api/posts/${postId}/favorite`, 'favorite')}
              disabled={isFavoriting}
              className="flex items-center gap-1.5 py-2 px-4 rounded-full bg-white/[0.03] border border-white/[0.08] text-white/70 hover:text-white text-xs font-semibold transition-all"
            >
              <Bookmark size={14} className="stroke-white/70" />
              <span>收藏</span>
            </motion.button>
          </div>

          {/* Blacklist button */}
          <motion.button
            whileTap={{ scale: 0.9 }}
            onClick={() => void callAction(`/api/posts/${postId}/blacklist`, 'blacklist')}
            disabled={isBlacklisting}
            className="flex items-center gap-1.5 py-2 px-3 rounded-full bg-white/[0.01] border border-white/[0.05] text-white/40 hover:text-red-400 hover:bg-red-500/5 hover:border-red-500/10 text-xs font-medium transition-all"
          >
            <EyeOff size={13} />
            <span>不感兴趣</span>
          </motion.button>
        </div>
      </div>

      {/* Comment Section Header */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-white flex items-center gap-1.5 px-1">
          <MessageSquare size={16} className="text-tgAccent" />
          <span>互动评论 ({detail.comments.length})</span>
        </h3>

        {/* Comment Bubbles List */}
        <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
          <AnimatePresence initial={false}>
            {detail.comments.length > 0 ? (
              detail.comments.map((comment, idx) => (
                <motion.div
                  key={comment.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.05 }}
                  className="flex items-start gap-3 p-3.5 rounded-2xl bg-white/[0.02] border border-white/[0.06]"
                >
                  {/* Avatar Placeholder */}
                  <div className="h-7 w-7 rounded-full bg-gradient-to-tr from-blue-500 to-tgAccent flex items-center justify-center text-[10px] font-bold text-white uppercase">
                    {idx % 3 === 0 ? 'U' : idx % 3 === 1 ? 'A' : 'T'}
                  </div>
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-white/80">
                        {comment.authorName ?? `匿名探索者 #${comment.id % 999}`}
                      </span>
                      <span className="text-[10px] text-white/40">
                        {new Date(comment.createdAt).toLocaleDateString('zh-CN', {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </span>
                    </div>
                    <p className="text-xs text-white/90 leading-relaxed">{comment.content}</p>
                  </div>
                </motion.div>
              ))
            ) : (
              <div className="py-8 text-center text-xs text-white/30">
                还没有评论呢，说句鼓励的话吧~
              </div>
            )}
          </AnimatePresence>
        </div>

        {/* Elegant Input & Send Container */}
        <div className="flex gap-2 p-1.5 rounded-2xl bg-white/[0.02] border border-white/[0.06] shadow-inner">
          <Input
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="写下你的真实看法..."
            className="flex-1 border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 text-xs px-3 h-10"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && content.trim()) {
                void callAction(`/api/posts/${postId}/comment`, 'comment', { content })
                setContent('')
              }
            }}
          />
          <Button
            size="sm"
            onClick={() => {
              if (content.trim()) {
                void callAction(`/api/posts/${postId}/comment`, 'comment', { content })
                setContent('')
              }
            }}
            className="h-10 px-4 rounded-xl bg-tgAccent text-black hover:opacity-95 font-semibold flex items-center gap-1 transition-all active:scale-95"
          >
            <Send size={12} />
            <span>发送</span>
          </Button>
        </div>
      </div>

      {/* Full Width Telegram Action Button */}
      <MainButton
        text="立即发起私聊预约"
        onClick={() =>
          window.Telegram?.WebApp?.openTelegramLink('https://t.me/' + (process.env.NEXT_PUBLIC_BOT_USERNAME ?? ''))
        }
      />
      <Navbar />
    </div>
  )
}

