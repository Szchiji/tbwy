'use client'

import { useState, useRef, useEffect } from 'react'
import Image from 'next/image'

type Props = {
  items: Array<{ id: number; src: string }>
}

export function PostGallery({ items }: Props) {
  const [activeIndex, setActiveIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleScroll = () => {
    if (!containerRef.current) return
    const { scrollLeft, clientWidth } = containerRef.current
    const index = Math.round(scrollLeft / clientWidth)
    setActiveIndex(index)
  }

  // Handle case where items count changes
  useEffect(() => {
    setActiveIndex(0)
  }, [items])

  if (!items || items.length === 0) {
    return (
      <div className="relative h-72 w-full flex items-center justify-center rounded-3xl bg-white/[0.02] border border-white/[0.08]">
        <span className="text-sm text-white/30">暂无媒体文件</span>
      </div>
    )
  }

  return (
    <div className="relative group w-full">
      {/* Horizontal Carousel */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-3 scroll-smooth no-scrollbar"
        style={{ scrollbarWidth: 'none' }}
      >
        {items.map((item) => (
          <div
            key={item.id}
            className="relative h-80 w-full shrink-0 snap-center overflow-hidden rounded-3xl border border-white/[0.06] shadow-lg shadow-black/20"
          >
            <Image
              src={item.src}
              alt="post media"
              fill
              sizes="(max-width: 768px) 100vw, 500px"
              className="object-cover transition-transform duration-500 hover:scale-102"
              loading="lazy"
              placeholder="blur"
              blurDataURL="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
            />
          </div>
        ))}
      </div>

      {/* Elegant Dot Indicators */}
      {items.length > 1 && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-black/40 backdrop-blur-md border border-white/10">
          {items.map((_, index) => (
            <span
              key={index}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                index === activeIndex ? 'w-4 bg-tgAccent' : 'w-1.5 bg-white/40'
              }`}
            />
          ))}
        </div>
      )}
    </div>
  )
}

