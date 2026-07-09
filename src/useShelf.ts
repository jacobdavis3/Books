import { useCallback, useEffect, useState } from 'react'
import type { Book } from './types'

const STORAGE_KEY = 'books-shelf'

function load(): Book[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function useShelf() {
  const [books, setBooks] = useState<Book[]>(load)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(books))
  }, [books])

  const addBook = useCallback((book: Book) => {
    setBooks((prev) =>
      prev.some((b) => b.isbn === book.isbn) ? prev : [book, ...prev]
    )
  }, [])

  const removeBook = useCallback((isbn: string) => {
    setBooks((prev) => prev.filter((b) => b.isbn !== isbn))
  }, [])

  const updateBook = useCallback(
    (isbn: string, patch: Partial<Pick<Book, 'library' | 'dueDate' | 'status'>>) => {
      setBooks((prev) =>
        prev.map((b) => (b.isbn === isbn ? { ...b, ...patch } : b))
      )
    },
    []
  )

  return { books, addBook, removeBook, updateBook }
}
