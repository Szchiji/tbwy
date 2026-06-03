import { prisma } from '@/lib/prisma'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

async function getAdminData() {
  const [postsTotal, usersTotal, pendingTotal, pending, settings] = await Promise.all([
    prisma.post.count(),
    prisma.user.count(),
    prisma.post.count({ where: { isApproved: false } }),
    prisma.post.findMany({ where: { isApproved: false }, orderBy: { date: 'desc' }, take: 20 }),
    prisma.setting.findMany({ orderBy: { key: 'asc' } }),
  ])
  return { postsTotal, usersTotal, pendingTotal, pending, settings }
}

export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<{ ADMIN_KEY?: string | string[] }>
}) {
  const resolvedSearchParams = await searchParams
  const keyValue = resolvedSearchParams.ADMIN_KEY
  const ADMIN_KEY = Array.isArray(keyValue) ? keyValue[0] : keyValue
  if (!ADMIN_KEY || ADMIN_KEY !== process.env.ADMIN_KEY) {
    return <div className="p-4 text-sm text-red-300">无权限访问管理后台。</div>
  }
  const data = await getAdminData()

  return (
    <div className="space-y-4 pb-10">
      <h1 className="text-lg font-semibold">管理后台</h1>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded-xl bg-white/10 p-3">帖子 {data.postsTotal}</div>
        <div className="rounded-xl bg-white/10 p-3">用户 {data.usersTotal}</div>
        <div className="rounded-xl bg-white/10 p-3">待审 {data.pendingTotal}</div>
      </div>
      <section className="space-y-2">
        <h2 className="text-sm">待审核帖子</h2>
        {data.pending.map((post) => (
          <form key={post.id} action={`/api/admin/posts/${post.id}/approve?ADMIN_KEY=${ADMIN_KEY}`} method="post" className="rounded-xl bg-white/10 p-3 text-sm">
            <p>{post.title ?? `帖子 #${post.id}`}</p>
            <div className="mt-2 flex gap-2">
              <Button name="approved" value="true" type="submit">通过</Button>
              <Button className="bg-rose-600" formAction={`/api/admin/posts/${post.id}?ADMIN_KEY=${ADMIN_KEY}`} formMethod="post">拒绝</Button>
            </div>
          </form>
        ))}
      </section>
      <section className="space-y-2">
        <h2 className="text-sm">设置管理</h2>
        {data.settings.map((setting) => (
          <form key={setting.key} action={`/api/admin/settings?ADMIN_KEY=${ADMIN_KEY}`} method="post" className="rounded-xl bg-white/10 p-3">
            <Input name="key" defaultValue={setting.key} readOnly className="mb-2" />
            <Input name="value" defaultValue={setting.value} />
            <Button className="mt-2" type="submit">保存</Button>
          </form>
        ))}
      </section>
    </div>
  )
}
