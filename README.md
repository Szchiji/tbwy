# tbwy Telegram Mini App (Next.js + Prisma)

## 技术栈

- Frontend: Next.js 15 (App Router) + React 19 + TypeScript + Tailwind CSS
- UI/State: shadcn/ui 风格基础组件 + Framer Motion + Zustand + TanStack Query
- Backend API: Next.js Route Handlers (TypeScript)
- Database: PostgreSQL + Prisma ORM
- Auth: Telegram initData HMAC-SHA256 + JWT
- Bot: grammy Webhook
- Deploy: Vercel（前端）+ Railway（后端/DB，兼容 Procfile）

## 本地开发

1. 安装依赖

```bash
npm install
```

2. 初始化数据库

```bash
npm run db:push
```

3. 启动开发环境

```bash
npm run dev
```

4. 生产构建

```bash
npm run build
npm run start
```

## Railway + Vercel 部署

### Vercel

- 导入仓库并设置环境变量
- Build Command: `npm run build`
- Start Command: `npm run start`

### Railway

- 创建 PostgreSQL 服务，获得 `DATABASE_URL`
- 在 Web 服务配置同样的环境变量
- `Procfile` 使用：

```procfile
web: npm start
```

## 环境变量

参考 `.env.example`：

- `TELEGRAM_BOT_TOKEN`, `MY_CHAT_ID`, `CHANNEL_ID`, `BOT_USERNAME`
- `NEXT_PUBLIC_BOT_USERNAME`, `ADMIN_KEY`, `NEXTAUTH_SECRET`, `BASE_URL`
- `DATABASE_URL`
- 可选存储/AI配置

## Telegram Bot 设置

1. 使用 BotFather 获取 `TELEGRAM_BOT_TOKEN`
2. 配置 Mini App URL（HTTPS）
3. 将 webhook 指向 `https://<domain>/api/webhook`
4. 在 Bot 中使用 `/start`、`/desc`、`/cancel`、`/notice`、`/sync`、`/admin`

## SQLite -> PostgreSQL 迁移简述

1. 导出旧 SQLite 数据（users/posts/comments/favorites/blacklist/settings）
2. 按 `prisma/schema.prisma` 字段映射转换（尤其主键、外键、时间字段）
3. 写入 PostgreSQL（可使用 Prisma Script 或 psql COPY）
4. 执行 `npm run db:push` 校验结构后切换生产连接串

## 目录结构

```text
app/
components/
lib/
prisma/
store/
hooks/
types/
```
