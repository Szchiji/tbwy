'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const tabs = [
  { href: '/', label: '首页' },
  { href: '/favorites', label: '收藏' },
  { href: '/upload', label: '投稿' },
  { href: '/profile', label: '我的' },
]

export function Navbar() {
  const pathname = usePathname()
  return (
    <nav className="fixed bottom-0 left-0 right-0 border-t border-white/20 bg-black/30 backdrop-blur-md">
      <div className="mx-auto flex max-w-md justify-around py-3 text-xs">
        {tabs.map((tab) => (
          <Link key={tab.href} href={tab.href} className={pathname === tab.href ? 'text-tgAccent' : 'text-white/80'}>
            {tab.label}
          </Link>
        ))}
      </div>
    </nav>
  )
}
