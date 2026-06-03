export type PostListItem = {
  id: number
  title: string | null
  text: string | null
  likes: number
  date: string
  firstMedia: string | null
  thumbnail: string | null
  mediaGroupId: string | null
  tags: string
  commentsCount: number
}

export type TelegramUser = {
  id: number
  username?: string
  first_name?: string
  last_name?: string
  photo_url?: string
}
