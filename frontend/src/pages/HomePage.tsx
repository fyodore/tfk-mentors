import { Link } from 'react-router-dom'

import { AppHeader } from '../components/AppHeader.tsx'
import { SITE_PAGE_CARDS } from '../nav.js'

export default function HomePage() {
  return (
    <>
      <AppHeader />

      <main className="panel home-panel">
        <h2 id="pages-heading">Site pages</h2>
        <p className="home-intro muted">
          Choose a destination below. Links open inside this app (no full page
          reload).
        </p>

        <nav className="home-nav" aria-labelledby="pages-heading">
          <ul className="home-page-list">
            {SITE_PAGE_CARDS.map((page) => (
              <li key={page.path}>
                <Link className="home-page-card" to={page.path}>
                  <span className="home-page-card-title">{page.title}</span>
                  <span className="home-page-card-desc muted">
                    {page.description}
                  </span>
                  <span className="home-page-card-path" aria-hidden>
                    {page.path}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </main>
    </>
  )
}
