# Matrix Hub - Telegram 媒体内容管理系统

一个基于 Flask 和 Telegram Bot API 的媒体内容管理和展示平台。

## 功能特性

### 核心功能

1. **Telegram 集成**
   - 通过 Telegram Bot 接收频道消息和用户投稿
   - 自动下载并存储媒体文件（图片和视频）
   - 支持媒体组（相册）的统一管理
   - Webhook 方式接收实时更新

2. **内容管理**
   - 自动同步 Telegram 频道历史内容
   - 投稿审核机制（管理员可批准或拒绝）
   - 黑名单功能，屏蔽特定用户
   - 支持内容编辑和更新

3. **Web 前端展示**
   - 响应式设计，适配移动端和桌面端
   - 网格布局展示媒体内容
   - 视频和图片预览
   - 内容搜索功能
   - 公告栏显示

4. **详情页功能**
   - 媒体相册完整展示
   - 点赞系统（带本地持久化）
   - 评论功能
   - 暗色主题设计

5. **数据持久化**
   - SQLite 数据库存储
   - 自动数据库迁移
   - 支持 Railway Volume 路径适配

## 技术栈

- **后端**: Flask + Python 3.10
- **机器人**: pyTelegramBotAPI
- **数据库**: SQLite3
- **前端**: Tailwind CSS
- **部署**: Gunicorn + Railway/Heroku

## 环境变量配置

创建 `.env` 文件或在部署平台设置以下环境变量：

```bash
TELEGRAM_TOKEN=your_bot_token        # Telegram Bot Token
MY_CHAT_ID=your_admin_chat_id       # 管理员聊天 ID
CHANNEL_ID=your_channel_id          # 频道 ID
BASE_URL=https://your-domain.com    # 应用的公网 URL（用于 Webhook）
PORT=5000                            # 端口号（可选，默认 5000）
```

## 安装与运行

### 本地开发

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 设置环境变量（参考上方配置）

3. 运行应用：
```bash
python app.py
```

### 生产部署

使用 Gunicorn 启动：
```bash
gunicorn app:app
```

## 管理员命令

在 Telegram 中向机器人发送以下命令：

- `/notice <内容>` - 更新网站公告
- `/desc <post_id> <描述文字>` - 为指定帖子添加自定义描述（显示在详情页点赞按钮上方）
- `/sync` - 同步频道最近 50 条内容

## 数据库结构

### posts 表
- `id`: 主键
- `msg_id`: Telegram 消息 ID
- `text`: 内容文本
- `title`: 标题（官方/投稿）
- `date`: 发布日期
- `likes`: 点赞数
- `blacklist_count`: 拉黑数量
- `custom_description`: 管理员自定义描述
- `media_group_id`: 媒体组 ID
- `first_media`: 首张媒体路径
- `is_approved`: 审核状态
- `user_id`: 用户 ID

### blacklist 表
- `user_id`: 黑名单用户 ID
- `date`: 添加日期

### user_blacklist 表
- `user_id`: 拉黑操作的用户ID（客户端生成）
- `post_id`: 被拉黑的帖子ID
- `date`: 拉黑日期

### user_favorites 表
- `user_id`: 用户ID（客户端生成）
- `post_id`: 收藏的帖子ID
- `date`: 收藏日期

### settings 表
- `key`: 设置键
- `value`: 设置值

### comments 表
- `id`: 主键
- `post_id`: 关联的帖子 ID
- `content`: 评论内容
- `date`: 评论日期
- `user_id`: 评论者用户ID（客户端生成）

## API 端点

### 页面路由
- `GET /` - 首页（支持分页参数 `?page=`，搜索参数 `?q=`，用户ID参数 `?user_id=`）
- `GET /post/<post_id>` - 内容详情页
- `GET /favorites` - 收藏页面（需要 `?user_id=` 参数）

### API 接口
- `POST /api/like/<post_id>` - 点赞（支持速率限制：10次/分钟）
- `POST /api/blacklist/<post_id>` - 拉黑内容（需要传递 user_id）
- `POST /api/comment/<post_id>` - 发表评论（支持速率限制：5次/分钟，自动 XSS 防护）
- `DELETE /api/comment/<comment_id>` - 删除评论（需要用户授权）
- `POST /api/favorite/<post_id>` - 添加到收藏
- `DELETE /api/favorite/<post_id>` - 从收藏移除
- `GET /api/favorites` - 获取用户的收藏列表
- `POST /webhook` - Telegram Webhook 接收端点
- `GET /uploads/<filename>` - 媒体文件服务

## 文件结构

```
tbwy/
├── app.py              # 主应用文件
├── requirements.txt    # Python 依赖
├── runtime.txt         # Python 版本
├── Procfile           # 部署配置
├── templates/         # HTML 模板
│   ├── index.html    # 首页（带底部导航和分页）
│   ├── detail.html   # 详情页（带收藏、分享、图片放大等功能）
│   └── favorites.html # 收藏页面
├── data/             # 数据目录（自动创建）
│   ├── data.db      # SQLite 数据库
│   └── uploads/     # 媒体文件存储
└── .gitignore        # Git 忽略配置
```

## 已修复的问题

### 2024 年修复
1. **InlineKeyboardButton 参数错误**: 将 `callback_query_data` 修正为 `callback_data`
2. **模板变量引用错误**: 修正 `detail.html` 中的 `m.first_media` 为 `m`（all_media 是字符串列表）

### 2026 年新增功能
1. **卡片布局优化**: 首页卡片采用横向布局（左图右文），高度从 240px 减小到 128px
2. **视频封面显示**: 添加 `preload="metadata"` 和时间戳参数以显示视频第一帧作为封面
3. **用户拉黑功能**: 
   - 用户可以拉黑不喜欢的内容
   - 拉黑后该内容不再在首页显示
   - 全站显示每个帖子的拉黑数量
   - 拉黑按钮显示在点赞按钮旁边
4. **管理员自定义描述**: 管理员可通过 `/desc` 命令为帖子添加自定义描述，显示在详情页点赞按钮上方
5. **用户识别系统**: 使用本地存储生成唯一用户ID，用于追踪点赞和拉黑记录
6. **收藏功能** (2026-01-16 新增):
   - 用户可以收藏喜欢的帖子
   - 收藏数据存储在数据库中
   - 提供专门的收藏页面查看所有收藏
   - 详情页一键收藏/取消收藏
7. **分页功能**: 首页支持分页浏览，每页显示 20 条内容
8. **底部导航栏**: 新增底部导航栏（首页、搜索、收藏、我的）
9. **分享功能**: 详情页可一键复制链接分享
10. **图片放大预览**: 图片支持点击放大查看（Lightbox 效果）
11. **返回顶部按钮**: 详情页滚动时显示返回顶部按钮
12. **安全增强**:
    - XSS 防护：评论内容自动转义 HTML
    - API 请求频率限制（防止滥用）
    - 评论删除权限验证（只能删除自己的评论）
13. **性能优化**:
    - 数据库索引优化
    - 分页查询提升加载速度

## License

MIT
