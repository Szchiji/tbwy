import { create } from 'zustand'

type FilterState = {
  search: string
  type: 'all' | 'image' | 'video'
  sort: 'latest' | 'hot'
  tag: string
  setSearch: (search: string) => void
  setType: (type: 'all' | 'image' | 'video') => void
  setSort: (sort: 'latest' | 'hot') => void
  setTag: (tag: string) => void
}

export const useAppStore = create<FilterState>((set) => ({
  search: '',
  type: 'all',
  sort: 'latest',
  tag: '',
  setSearch: (search) => set({ search }),
  setType: (type) => set({ type }),
  setSort: (sort) => set({ sort }),
  setTag: (tag) => set({ tag }),
}))
