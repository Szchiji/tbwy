'use client'

import { motion } from 'framer-motion'
import Image from 'next/image'
import Link from 'next/link'
import type { PostListItem } from '@/types'

export function PostCard({ post }: { post: PostListItem }) {
  const imageSrc = post.thumbnail ?? post.firstMedia ?? '/placeholder.png'
  return (
    <motion.div whileHover={{ y: -3 }} className="rounded-2xl border border-white/20 bg-white/10 backdrop-blur-md">
      <Link href={`/post/${post.id}`}>
        <div className="relative h-48 w-full overflow-hidden rounded-t-2xl">
          <Image
            src={imageSrc}
            alt={post.title ?? 'post'}
            fill
            className="object-cover"
            loading="lazy"
            placeholder="blur"
            blurDataURL="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
          />
        </div>
        <div className="p-3">
          <h3 className="line-clamp-1 text-sm font-medium">{post.title ?? '未命名帖子'}</h3>
          <p className="mt-2 text-xs text-white/80">👍 {post.likes} · 💬 {post.commentsCount}</p>
        </div>
      </Link>
    </motion.div>
  )
}
