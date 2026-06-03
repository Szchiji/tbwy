'use client'

import { Navbar } from '@/components/Navbar'
import { Card } from '@/components/ui/card'
import { useTelegram } from '@/hooks/useTelegram'

export default function ProfilePage() {
  const { userId } = useTelegram()

  return (
    <>
      <h1 className="mb-4 text-lg font-semibold">个人中心</h1>
      <Card className="p-4 text-sm">当前用户：{userId}</Card>
      <Navbar />
    </>
  )
}
