import type { Book } from './types'

const API_KEY = import.meta.env.VITE_GOOGLE_BOOKS_API_KEY

export class BookNotFoundError extends Error {}

export async function lookupByIsbn(isbn: string): Promise<Book> {
  const url = new URL('https://www.googleapis.com/books/v1/volumes')
  url.searchParams.set('q', `isbn:${isbn}`)
  if (API_KEY) url.searchParams.set('key', API_KEY)

  const res = await fetch(url.toString())
  if (!res.ok) {
    throw new Error(`Google Books API error: ${res.status}`)
  }

  const data = await res.json()
  const item = data.items?.[0]
  if (!item) {
    throw new BookNotFoundError(`No book found for ISBN ${isbn}`)
  }

  const info = item.volumeInfo
  return {
    isbn,
    title: info.title ?? 'Unknown title',
    authors: info.authors ?? [],
    thumbnail: info.imageLinks?.thumbnail,
    publishedDate: info.publishedDate,
    addedAt: new Date().toISOString(),
    status: 'out',
  }
}
