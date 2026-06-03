'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import { MainButton } from '@/components/MainButton'
import { Navbar } from '@/components/Navbar'
import { PostGallery } from '@/components/PostGallery'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useTelegram } from '@/hooks/useTelegram'

type Comment = { id: number; content: string; createdAt: string }
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
  const [detail, setDetail] = useState<Detail | null>(null)
  const [content, setContent] = useState('')
  const { userId, initData, haptic } = useTelegram()

  const postId = useMemo(() => Number(params.id), [params.id])

  useEffect(() => {
    fetch(`/api/posts/${postId}`)
      .then((res) => res.json())
      .then((json: Detail) => setDetail(json))
      .catch(() => undefined)
  }, [postId])

  if (!detail) return <div>加载中...</div>

  const callAction = async (path: string, method = 'POST', body: Record<string, string> = {}) => {
    haptic('medium')
    await fetch(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId, initData, ...body }),
    })
    const refreshed = await fetch(`/api/posts/${postId}`).then((r) => r.json() as Promise<Detail>)
    setDetail(refreshed)
  }

  return (
    <div className="space-y-4 pb-16">
      <h1 className="text-lg font-semibold">{detail.title ?? '帖子详情'}</h1>
      <PostGallery items={detail.media} />
      <p className="text-sm text-white/90">{detail.text}</p>
      <div className="flex gap-2">
        <Button onClick={() => void callAction(`/api/posts/${postId}/like`)}>点赞</Button>
        <Button onClick={() => void callAction(`/api/posts/${postId}/favorite`)}>收藏</Button>
        <Button onClick={() => void callAction(`/api/posts/${postId}/blacklist`)}>拉黑</Button>
      </div>
      <div className="space-y-2">
        {detail.comments.map((comment) => (
          <div key={comment.id} className="rounded-xl bg-white/10 p-2 text-sm">
            {comment.content}
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <Input value={content} onChange={(e) => setContent(e.target.value)} placeholder="说点什么..." />
        <Button
          onClick={() => {
            void callAction(`/api/posts/${postId}/comment`, 'POST', { content })
            setContent('')
          }}
        >
          发送
        </Button>
      </div>
      <MainButton text="立即预约" onClick={() => window.Telegram?.WebApp?.openTelegramLink('https://t.me/' + (process.env.NEXT_PUBLIC_BOT_USERNAME ?? ''))} />
      <Navbar />
    </div>
  )
}
