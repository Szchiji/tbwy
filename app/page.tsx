'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, SlidersHorizontal, X, Grid, Film, Image as ImageIcon, Flame, Clock, Hash } from 'lucide-react'
import { PostCard } from '@/components/PostCard'
import { Navbar } from '@/components/Navbar'
import { Input } from '@/components/ui/input'
import { usePosts } from '@/hooks/usePosts'
import { useAppStore } from '@/store/useAppStore'

function PostCardSkeleton() {
  return (
    <div className="relative h-52 w-full overflow-hidden rounded-3xl border border-white/[0.04] bg-white/[0.01] shadow-sm">
      <div className="absolute inset-0 animate-shimmer" />
      <div className="absolute bottom-0 left-0 right-0 p-3 space-y-2 bg-gradient-to-t from-black/60 to-transparent">
        <div className="h-4 w-3/4 rounded-full bg-white/10" />
        <div className="h-3 w-1/3 rounded-full bg-white/10" />
      </div>
    </div>
  )
}

export default function HomePage() {
  const loadRef = useRef<HTMLDivElement | null>(null)
  const [isFilterOpen, setIsFilterOpen] = useState(false)
  const { search, type, sort, tag, setSearch, setType, setSort, setTag } = useAppStore()
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = usePosts()

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
      {/* Header section with Premium Search & Filter Trigger */}
      <section className="sticky top-0 z-40 bg-tgBg/80 backdrop-blur-md pb-3 pt-1">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40" />
            <Input
              placeholder="搜索感兴趣的内容..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10 pr-4 py-5 rounded-2xl bg-white/[0.03] border-white/[0.08] focus:border-tgAccent/50 focus:bg-white/[0.05] transition-all text-sm"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-full bg-white/10 text-white/60 hover:text-white"
              >
                <X size={12} />
              </button>
            )}
          </div>
          <button
            onClick={() => setIsFilterOpen(true)}
            className={`p-3 rounded-2xl border transition-all duration-300 relative ${
              type !== 'all' || sort !== 'latest' || tag
                ? 'bg-tgAccent/10 border-tgAccent/30 text-tgAccent'
                : 'bg-white/[0.03] border-white/[0.08] text-white/70 hover:text-white'
            }`}
          >
            <SlidersHorizontal size={18} />
            {(type !== 'all' || sort !== 'latest' || tag) && (
              <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-tgAccent text-[8px] font-bold text-black ring-2 ring-tgBg">
                !
              </span>
            )}
          </button>
        </div>

        {/* Active tags display if filtered */}
        {(type !== 'all' || sort !== 'latest' || tag) && (
          <div className="mt-2.5 flex flex-wrap gap-1.5 text-[10px]">
            {type !== 'all' && (
              <span className="px-2 py-0.5 rounded-full bg-tgAccent/10 text-tgAccent border border-tgAccent/20 flex items-center gap-1">
                {type === 'image' ? <ImageIcon size={10} /> : <Film size={10} />}
                {type === 'image' ? '图片' : '视频'}
              </span>
            )}
            {sort !== 'latest' && (
              <span className="px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20 flex items-center gap-1">
                <Flame size={10} />
                最热优先
              </span>
            )}
            {tag && (
              <span className="px-2 py-0.5 rounded-full bg-pink-500/10 text-pink-400 border border-pink-500/20 flex items-center gap-1">
                <Hash size={10} />
                {tag}
              </span>
            )}
          </div>
        )}
      </section>

      {/* Main Grid Flow */}
      <section className="mt-1 grid grid-cols-2 gap-3 min-h-[50vh]">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => <PostCardSkeleton key={i} />)
        ) : items.length > 0 ? (
          items.map((post) => <PostCard key={post.id} post={post} />)
        ) : (
          <div className="col-span-2 py-20 text-center text-sm text-white/40">
            暂无匹配的数据，换个词试试吧
          </div>
        )}
      </section>

      {/* Infinity Load Loader */}
      <div ref={loadRef} className="h-24 flex items-center justify-center text-xs text-white/40 pb-20">
        {isFetchingNextPage ? (
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-tgAccent border-t-transparent" />
            <span>智能加载中...</span>
          </div>
        ) : hasNextPage ? (
          '继续下滑加载更多优秀内容'
        ) : (
          items.length > 0 && '— 已展示全部内容 —'
        )}
      </div>

      {/* Premium Sliding Filter Drawer */}
      <AnimatePresence>
        {isFilterOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsFilterOpen(false)}
              className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            />

            {/* Bottom Sheet */}
            <motion.div
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 350 }}
              className="fixed bottom-0 left-0 right-0 z-50 mx-auto max-w-md glass-card rounded-t-3xl p-6 pb-8 shadow-2xl shadow-black/80"
            >
              {/* Drag Handle Indicator */}
              <div className="mx-auto -mt-2 mb-4 h-1.5 w-12 rounded-full bg-white/20" />

              <div className="flex items-center justify-between mb-5">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <SlidersHorizontal size={18} className="text-tgAccent" />
                  条件过滤器
                </h3>
                <button
                  onClick={() => setIsFilterOpen(false)}
                  className="p-1.5 rounded-full bg-white/5 text-white/60 hover:text-white"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="space-y-5 text-sm">
                {/* Content Type */}
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-white/50 tracking-wider">内容类型</span>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { key: 'all', label: '全部', icon: Grid },
                      { key: 'image', label: '图片', icon: ImageIcon },
                      { key: 'video', label: '视频', icon: Film },
                    ].map((btn) => {
                      const Icon = btn.icon
                      const active = type === btn.key
                      return (
                        <button
                          key={btn.key}
                          onClick={() => setType(btn.key as any)}
                          className={`py-2.5 px-3 rounded-xl flex items-center justify-center gap-1.5 border font-medium transition-all ${
                            active
                              ? 'bg-tgAccent text-black border-tgAccent shadow-lg shadow-tgAccent/20'
                              : 'bg-white/[0.02] border-white/[0.08] text-white/80 hover:bg-white/[0.05]'
                          }`}
                        >
                          <Icon size={14} />
                          {btn.label}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Sort Order */}
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-white/50 tracking-wider">排序方式</span>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { key: 'latest', label: '最新发布', icon: Clock },
                      { key: 'hot', label: '最热互动', icon: Flame },
                    ].map((btn) => {
                      const Icon = btn.icon
                      const active = sort === btn.key
                      return (
                        <button
                          key={btn.key}
                          onClick={() => setSort(btn.key as any)}
                          className={`py-2.5 px-3 rounded-xl flex items-center justify-center gap-1.5 border font-medium transition-all ${
                            active
                              ? 'bg-tgAccent text-black border-tgAccent shadow-lg shadow-tgAccent/20'
                              : 'bg-white/[0.02] border-white/[0.08] text-white/80 hover:bg-white/[0.05]'
                          }`}
                        >
                          <Icon size={14} />
                          {btn.label}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Tag Input */}
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-white/50 tracking-wider">专属标签</span>
                  <div className="relative">
                    <Hash size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40" />
                    <Input
                      placeholder="例如：生活, 艺术, 运动..."
                      value={tag}
                      onChange={(e) => setTag(e.target.value)}
                      className="pl-9 rounded-xl bg-white/[0.02] border-white/[0.08] focus:border-tgAccent/40 transition-all text-sm"
                    />
                  </div>
                </div>

                {/* Submit / Reset Actions */}
                <div className="pt-2 flex gap-3">
                  <button
                    onClick={() => {
                      setType('all')
                      setSort('latest')
                      setTag('')
                    }}
                    className="flex-1 py-3 rounded-xl border border-white/[0.08] bg-white/[0.01] text-white/70 font-semibold transition-all hover:bg-white/[0.04]"
                  >
                    重置
                  </button>
                  <button
                    onClick={() => setIsFilterOpen(false)}
                    className="flex-[2] py-3 rounded-xl bg-gradient-to-r from-blue-500 to-tgAccent text-white font-semibold transition-all hover:opacity-90 shadow-lg shadow-blue-500/20"
                  >
                    确认应用
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <Navbar />
    </>
  )
}

