export type BookStatus = 'out' | 'returned'

export interface Book {
  isbn: string
  title: string
  authors: string[]
  thumbnail?: string
  publishedDate?: string
  addedAt: string
  library?: string
  dueDate?: string
  status: BookStatus
}

export const LIBRARIES = ['NYPL', 'NY Society Library', 'DCPL', 'Princeton']
