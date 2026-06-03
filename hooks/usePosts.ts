'use client'

import { useInfiniteQuery } from '@tanstack/react-query'
import { useAppStore } from '@/store/useAppStore'
import type { PostListItem } from '@/types'

type PostsResponse = {
  items: PostListItem[]
  nextCursor: string | null
}

export function usePosts() {
  const { search, type, sort, tag } = useAppStore()

  return useInfiniteQuery<PostsResponse>({
    queryKey: ['posts', search, type, sort, tag],
    initialPageParam: '',
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams({
        cursor: String(pageParam),
        search,
        type,
        sort,
        tag,
      })
      const res = await fetch(`/api/posts?${params.toString()}`)
      if (!res.ok) {
        throw new Error('Failed to load posts')
      }
      return (await res.json()) as PostsResponse
    },
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  })
}
