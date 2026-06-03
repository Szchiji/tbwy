'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { motion } from 'framer-motion'
import { Home, Heart, PlusCircle, User } from 'lucide-react'

const tabs = [
  { href: '/', label: '首页', icon: Home },
  { href: '/favorites', label: '收藏', icon: Heart },
  { href: '/upload', label: '投稿', icon: PlusCircle },
  { href: '/profile', label: '我的', icon: User },
]

export function Navbar() {
  const pathname = usePathname()

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 mx-auto max-w-md">
      <nav className="glass-navbar rounded-2xl px-2 py-2 shadow-lg shadow-black/40">
        <div className="flex justify-around items-center">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const isActive = pathname === tab.href

            return (
              <Link
                key={tab.href}
                href={tab.href}
                className="relative flex flex-col items-center justify-center py-1.5 px-3 rounded-xl transition-all duration-300 outline-none"
              >
                {isActive && (
                  <motion.div
                    layoutId="activeTabGlow"
                    className="absolute inset-0 bg-white/[0.04] rounded-xl"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
                <motion.div
                  whileTap={{ scale: 0.9 }}
                  className={`relative z-10 flex flex-col items-center gap-1 ${
                    isActive ? 'text-tgAccent' : 'text-white/50 hover:text-white/80'
                  }`}
                >
                  <Icon
                    size={20}
                    className={`transition-all duration-300 ${
                      isActive ? 'stroke-[2.5px] drop-shadow-[0_0_8px_var(--tg-accent)]' : 'stroke-[1.8px]'
                    }`}
                  />
                  <span className="text-[10px] font-medium tracking-wide">{tab.label}</span>
                </motion.div>
                {isActive && (
                  <motion.span
                    layoutId="activeIndicator"
                    className="absolute -bottom-1 h-1 w-5 rounded-full bg-tgAccent"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
              </Link>
            )
          })}
        </div>
      </nav>
    </div>
  )
}

