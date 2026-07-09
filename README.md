# 📚 Jacob's Books

A tiny, install-on-your-phone library tracker for the whole family. Scan a
barcode, tell it where the book came from and when it's due back, and never
lose track of a due date again.

**Live app:** [jacobdavis3.github.io/Books](https://jacobdavis3.github.io/Books/)

---

## ✨ What it does

- **Scan or type an ISBN** — point your phone's camera at the barcode on the
  back of a book, or just type the number in by hand.
- **Auto-lookup** — pulls the title, authors, cover art, and publish year
  from the Google Books API the moment you scan.
- **Pick a library + due date** — choose from NYPL, NY Society Library,
  DCPL, or Princeton, and set when it's due, before it ever hits your shelf.
- **See every due date at a glance** — a dedicated tab lists everything
  that's checked out, sorted soonest-due-first, with color-coded badges
  (green = fine, orange = due soon, red = overdue).
- **Two-step returns** — no accidental taps. Mark a book returned with a
  confirm step, and it moves to a collapsible "Returned" history you can
  undo from.
- **Edit anytime** — tap Edit on any book to change its library or due date
  without re-scanning.
- **Feels like a real app** — installable straight to your iPhone home
  screen, full-screen, with its own icon.

## 📱 Add it to your home screen

1. Open the [live link](https://jacobdavis3.github.io/Books/) in **Safari**
   on your iPhone (has to be Safari for this to work).
2. Tap the **Share** button → **Add to Home Screen** → **Add**.
3. Launch it from your home screen like any other app.

> Heads up: books are stored locally on each device (`localStorage`), so
> your phone and someone else's phone won't share a list — yet.

## 🛠 Running it locally

```bash
npm install
npm run dev
```

Grab a free API key from the
[Google Books API](https://console.cloud.google.com/apis/library/books.googleapis.com)
and drop it in a `.env` file:

```bash
cp .env.example .env
# then edit .env:
VITE_GOOGLE_BOOKS_API_KEY=your-key-here
```

Other scripts:

```bash
npm run build    # type-check and build for production
npm run preview  # preview the production build locally
npm run lint     # run oxlint
```

## 🚀 Deployment

Every push to `main` triggers a GitHub Actions workflow
(`.github/workflows/deploy.yml`) that builds the app and publishes it to
GitHub Pages. No manual steps beyond the initial repo setup.

## 🧰 Built with

- [React](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- [Vite](https://vite.dev/)
- [@zxing/browser](https://github.com/zxing-js/browser) for barcode scanning
- [Google Books API](https://developers.google.com/books) for lookups
