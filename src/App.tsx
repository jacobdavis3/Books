import { useState } from 'react'
import { Scanner } from './Scanner'
import { useShelf } from './useShelf'
import { lookupByIsbn, BookNotFoundError } from './googleBooks'
import './App.css'

function App() {
  const { books, addBook, removeBook } = useShelf()
  const [scanning, setScanning] = useState(false)
  const [manualIsbn, setManualIsbn] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleIsbn(isbn: string) {
    if (busy) return
    setBusy(true)
    setStatus(`Looking up ${isbn}...`)
    try {
      const book = await lookupByIsbn(isbn)
      addBook(book)
      setStatus(`Added "${book.title}"`)
      setScanning(false)
    } catch (err) {
      setStatus(
        err instanceof BookNotFoundError
          ? `No book found for ISBN ${isbn}`
          : 'Lookup failed, try again'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <header>
        <h1>My Shelf</h1>
        <button onClick={() => setScanning((s) => !s)}>
          {scanning ? 'Cancel scan' : 'Scan a book'}
        </button>
      </header>

      {scanning && <Scanner onDetected={handleIsbn} />}

      <form
        className="manual-entry"
        onSubmit={(e) => {
          e.preventDefault()
          if (manualIsbn.trim()) {
            handleIsbn(manualIsbn.trim())
            setManualIsbn('')
          }
        }}
      >
        <input
          value={manualIsbn}
          onChange={(e) => setManualIsbn(e.target.value)}
          placeholder="Or type an ISBN"
          inputMode="numeric"
        />
        <button type="submit" disabled={busy}>
          Add
        </button>
      </form>

      {status && <p className="status">{status}</p>}

      <ul className="shelf">
        {books.map((book) => (
          <li key={book.isbn} className="book-card">
            {book.thumbnail && <img src={book.thumbnail} alt="" />}
            <div className="book-info">
              <h3>{book.title}</h3>
              <p>{book.authors.join(', ')}</p>
              {book.publishedDate && <p className="year">{book.publishedDate}</p>}
            </div>
            <button className="remove" onClick={() => removeBook(book.isbn)}>
              &times;
            </button>
          </li>
        ))}
        {books.length === 0 && <p className="empty">Your shelf is empty. Scan a book to get started.</p>}
      </ul>
    </div>
  )
}

export default App
