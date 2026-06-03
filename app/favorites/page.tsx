'use client'

import { useEffect, useState } from 'react'
import { Navbar } from '@/components/Navbar'
import { PostCard } from '@/components/PostCard'
import { useTelegram } from '@/hooks/useTelegram'
import type { PostListItem } from '@/types'

export default function FavoritesPage() {
  const { userId } = useTelegram()
  const [posts, setPosts] = useState<PostListItem[]>([])

  useEffect(() => {
    fetch(`/api/posts?favoritesOf=${userId}`)
      .then((r) => r.json())
      .then((json: { items: PostListItem[] }) => setPosts(json.items))
      .catch(() => undefined)
  }, [userId])

  return (
    <>
      <h1 className="mb-4 text-lg font-semibold">我的收藏</h1>
      <div className="grid grid-cols-2 gap-3">
        {posts.map((post) => (
          <PostCard key={post.id} post={post} />
        ))}
      </div>
      <Navbar />
    </>
  )
}
