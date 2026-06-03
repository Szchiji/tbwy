'use client'

import { useCallback, useEffect, useRef } from 'react'
import { PostCard } from '@/components/PostCard'
import { Navbar } from '@/components/Navbar'
import { Input } from '@/components/ui/input'
import { usePosts } from '@/hooks/usePosts'
import { useAppStore } from '@/store/useAppStore'

export default function HomePage() {
  const loadRef = useRef<HTMLDivElement | null>(null)
  const { search, type, sort, tag, setSearch, setType, setSort, setTag } = useAppStore()
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = usePosts()

  const onIntersect = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
        void fetchNextPage()
      }
    },
    [fetchNextPage, hasNextPage, isFetchingNextPage],
  )

  useEffect(() => {
    const observer = new IntersectionObserver(onIntersect, { threshold: 0.2 })
    if (loadRef.current) observer.observe(loadRef.current)
    return () => observer.disconnect()
  }, [onIntersect])

  const items = data?.pages.flatMap((p) => p.items) ?? []

  return (
    <>
      <section className="space-y-3">
        <Input placeholder="搜索标题或描述" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="grid grid-cols-2 gap-2 text-xs">
          <select className="rounded-xl bg-white/10 p-2" value={type} onChange={(e) => setType(e.target.value as 'all' | 'image' | 'video')}>
            <option value="all">全部类型</option>
            <option value="image">图片</option>
            <option value="video">视频</option>
          </select>
          <select className="rounded-xl bg-white/10 p-2" value={sort} onChange={(e) => setSort(e.target.value as 'latest' | 'hot')}>
            <option value="latest">最新</option>
            <option value="hot">最热</option>
          </select>
          <Input placeholder="标签（逗号分隔）" value={tag} onChange={(e) => setTag(e.target.value)} className="col-span-2" />
        </div>
      </section>
      <section className="mt-4 grid grid-cols-2 gap-3">
        {items.map((post) => (
          <PostCard key={post.id} post={post} />
        ))}
      </section>
      <div ref={loadRef} className="h-10 text-center text-xs text-white/70">{isFetchingNextPage ? '加载中...' : '继续下滑加载'}</div>
      <Navbar />
    </>
  )
}
