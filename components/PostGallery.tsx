'use client'

import Image from 'next/image'

type Props = {
  items: Array<{ id: number; src: string }>
}

export function PostGallery({ items }: Props) {
  return (
    <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2">
      {items.map((item) => (
        <div key={item.id} className="relative h-72 w-72 snap-center overflow-hidden rounded-2xl">
          <Image
            src={item.src}
            alt="post media"
            fill
            className="object-cover"
            loading="lazy"
            placeholder="blur"
            blurDataURL="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
          />
        </div>
      ))}
    </div>
  )
}
