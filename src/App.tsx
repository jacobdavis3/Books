import { useMemo, useState } from 'react'
import { Scanner } from './Scanner'
import { useShelf } from './useShelf'
import { lookupByIsbn, BookNotFoundError } from './googleBooks'
import { LIBRARIES, type Book } from './types'
import './App.css'

function parseLocalDate(dateStr: string): Date {
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function formatDueDate(dateStr: string): string {
  return parseLocalDate(dateStr).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
  })
}

function dueStatus(dueDate?: string): { label: string; className: string } {
  if (!dueDate) return { label: 'Not set', className: 'due-none' }

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const due = parseLocalDate(dueDate)
  const days = Math.round((due.getTime() - today.getTime()) / 86_400_000)
  const formatted = formatDueDate(dueDate)

  if (days < 0) return { label: `Overdue since ${formatted}`, className: 'due-overdue' }
  if (days === 0) return { label: `Today, ${formatted}`, className: 'due-soon' }
  if (days <= 3) return { label: `${formatted} (${days}d)`, className: 'due-soon' }
  return { label: formatted, className: 'due-ok' }
}

function sortByDueDate(books: Book[]): Book[] {
  return [...books].sort((a, b) => {
    if (!a.dueDate && !b.dueDate) return 0
    if (!a.dueDate) return 1
    if (!b.dueDate) return -1
    return a.dueDate.localeCompare(b.dueDate)
  })
}

type Tab = 'add' | 'books'

function App() {
  const { books, addBook, removeBook, updateBook } = useShelf()
  const [tab, setTab] = useState<Tab>('add')
  const [scanning, setScanning] = useState(false)
  const [manualIsbn, setManualIsbn] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmingReturn, setConfirmingReturn] = useState<string | null>(null)
  const [pendingBook, setPendingBook] = useState<Book | null>(null)
  const [editingIsbn, setEditingIsbn] = useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null)

  const checkedOut = useMemo(
    () => sortByDueDate(books.filter((b) => b.status !== 'returned')),
    [books]
  )
  const returned = useMemo(
    () => books.filter((b) => b.status === 'returned'),
    [books]
  )

  async function handleIsbn(isbn: string) {
    if (busy) return
    setBusy(true)
    setStatus(`Looking up ${isbn}...`)
    try {
      const book = await lookupByIsbn(isbn)
      setPendingBook(book)
      setStatus(null)
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

  function handleAddPending() {
    if (!pendingBook) return
    addBook(pendingBook)
    setStatus(`Added "${pendingBook.title}" to Due dates`)
    setPendingBook(null)
  }

  return (
    <div className="app">
      <header>
        <h1>
          <span className="title-gradient">Jacob's Books</span>
        </h1>
      </header>

      <nav className="tabs">
        <button
          className={tab === 'add' ? 'tab active' : 'tab'}
          onClick={() => setTab('add')}
        >
          Add a book
        </button>
        <button
          className={tab === 'books' ? 'tab active' : 'tab'}
          onClick={() => setTab('books')}
        >
          Due dates{checkedOut.length > 0 ? ` (${checkedOut.length})` : ''}
        </button>
      </nav>

      {tab === 'add' && (
        <section className="add-tab">
          {!pendingBook && (
            <>
              <button className="scan-toggle" onClick={() => setScanning((s) => !s)}>
                {scanning ? 'Cancel scan' : 'Scan a book'}
              </button>

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
                  Look up
                </button>
              </form>
            </>
          )}

          {status && <p className="status">{status}</p>}

          {pendingBook && (
            <div className="pending-card">
              {pendingBook.thumbnail && <img src={pendingBook.thumbnail} alt="" />}
              <div className="book-info">
                <h3>{pendingBook.title}</h3>
                <p>{pendingBook.authors.join(', ')}</p>
                {pendingBook.publishedDate && (
                  <p className="year">{pendingBook.publishedDate}</p>
                )}
                <div className="checkout-fields">
                  <select
                    className="library-input"
                    value={pendingBook.library ?? ''}
                    onChange={(e) =>
                      setPendingBook({ ...pendingBook, library: e.target.value })
                    }
                  >
                    <option value="">Select library</option>
                    {LIBRARIES.map((lib) => (
                      <option key={lib} value={lib}>
                        {lib}
                      </option>
                    ))}
                  </select>
                  <input
                    className="due-date-input"
                    type="date"
                    value={pendingBook.dueDate ?? ''}
                    onChange={(e) =>
                      setPendingBook({ ...pendingBook, dueDate: e.target.value })
                    }
                  />
                </div>
                <div className="pending-actions">
                  <button className="add-pending" onClick={handleAddPending}>
                    Add to Due dates
                  </button>
                  <button className="cancel-pending" onClick={() => setPendingBook(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
      )}

      {tab === 'books' && (
        <section className="books-tab">
          <ul className="shelf">
            {checkedOut.map((book) => {
              const due = dueStatus(book.dueDate)
              const confirming = confirmingReturn === book.isbn
              const editing = editingIsbn === book.isbn
              return (
                <li key={book.isbn} className="book-card">
                  {book.thumbnail && <img src={book.thumbnail} alt="" />}
                  <div className="book-info">
                    <div className="book-header">
                      <h3>{book.title}</h3>
                      <button
                        className="edit-button"
                        onClick={() => setEditingIsbn(editing ? null : book.isbn)}
                      >
                        {editing ? 'Done' : 'Edit'}
                      </button>
                    </div>
                    <p className="authors">{book.authors.join(', ')}</p>
                    {book.publishedDate && <p className="year">{book.publishedDate}</p>}

                    {editing ? (
                      <div className="checkout-fields">
                        <select
                          className="library-input"
                          value={book.library ?? ''}
                          onChange={(e) => updateBook(book.isbn, { library: e.target.value })}
                        >
                          <option value="">Select library</option>
                          {LIBRARIES.map((lib) => (
                            <option key={lib} value={lib}>
                              {lib}
                            </option>
                          ))}
                        </select>
                        <input
                          className="due-date-input"
                          type="date"
                          value={book.dueDate ?? ''}
                          onChange={(e) => updateBook(book.isbn, { dueDate: e.target.value })}
                        />
                      </div>
                    ) : (
                      <dl className="book-meta">
                        <div className="meta-row">
                          <dt>Library</dt>
                          <dd>{book.library || 'Not set'}</dd>
                        </div>
                        <div className="meta-row">
                          <dt>Due</dt>
                          <dd>
                            <span className={`due-badge ${due.className}`}>{due.label}</span>
                          </dd>
                        </div>
                      </dl>
                    )}
                  </div>
                  <div className="return-control">
                    {confirming ? (
                      <div className="return-confirm">
                        <span>Mark returned?</span>
                        <button
                          className="confirm-yes"
                          onClick={() => {
                            updateBook(book.isbn, { status: 'returned' })
                            setConfirmingReturn(null)
                          }}
                        >
                          Yes
                        </button>
                        <button className="confirm-no" onClick={() => setConfirmingReturn(null)}>
                          No
                        </button>
                      </div>
                    ) : (
                      <button className="return-button" onClick={() => setConfirmingReturn(book.isbn)}>
                        Mark returned
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
            {checkedOut.length === 0 && (
              <p className="empty">No books checked out. Add one from the first tab.</p>
            )}
          </ul>

          {returned.length > 0 && (
            <details className="returned-section">
              <summary>Returned ({returned.length})</summary>
              <ul className="shelf returned-list">
                {returned.map((book) => {
                  const confirmingDeleteThis = confirmingDelete === book.isbn
                  return (
                    <li key={book.isbn} className="book-card returned">
                      {book.thumbnail && <img src={book.thumbnail} alt="" />}
                      <div className="book-info">
                        <h3>{book.title}</h3>
                        <p>{book.library ?? 'Unknown library'}</p>
                      </div>
                      {confirmingDeleteThis ? (
                        <div className="return-confirm">
                          <span>Delete for good?</span>
                          <button
                            className="confirm-yes delete-yes"
                            onClick={() => {
                              removeBook(book.isbn)
                              setConfirmingDelete(null)
                            }}
                          >
                            Yes
                          </button>
                          <button className="confirm-no" onClick={() => setConfirmingDelete(null)}>
                            No
                          </button>
                        </div>
                      ) : (
                        <div className="returned-actions">
                          <button
                            className="undo-return"
                            onClick={() => updateBook(book.isbn, { status: 'out' })}
                          >
                            Undo
                          </button>
                          <button
                            className="delete-button"
                            onClick={() => setConfirmingDelete(book.isbn)}
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            </details>
          )}
        </section>
      )}
    </div>
  )
}

export default App
