'use client'

import { motion } from 'framer-motion'
import Image from 'next/image'
import Link from 'next/link'
import type { PostListItem } from '@/types'
import { Heart, MessageCircle } from 'lucide-react'

export function PostCard({ post }: { post: PostListItem }) {
  const imageSrc = post.thumbnail ?? post.firstMedia ?? '/placeholder.png'
  return (
    <motion.div
      whileHover={{ y: -4, scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="group relative overflow-hidden rounded-3xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-md transition-all duration-300 hover:border-white/[0.12] hover:bg-white/[0.04] shadow-md shadow-black/10"
    >
      <Link href={`/post/${post.id}`} className="block">
        <div className="relative h-52 w-full overflow-hidden">
          <Image
            src={imageSrc}
            alt={post.title ?? 'post'}
            fill
            sizes="(max-width: 768px) 50vw, 33vw"
            className="object-cover transition-transform duration-500 group-hover:scale-105"
            loading="lazy"
            placeholder="blur"
            blurDataURL="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-60 transition-opacity duration-300 group-hover:opacity-70" />
        </div>
        <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
          <h3 className="line-clamp-1 text-sm font-semibold tracking-wide text-white/95 group-hover:text-white transition-colors duration-200">
            {post.title ?? '未命名帖子'}
          </h3>
          <div className="mt-1.5 flex items-center gap-3 text-[11px] text-white/70">
            <span className="flex items-center gap-1">
              <Heart size={12} className="fill-tgAccent/20 stroke-tgAccent" />
              <span className="font-semibold">{post.likes}</span>
            </span>
            <span className="flex items-center gap-1">
              <MessageCircle size={12} className="stroke-white/60" />
              <span className="font-semibold">{post.commentsCount}</span>
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  )
}

