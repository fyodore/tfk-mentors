import { NavLink } from 'react-router-dom'

import { SITE_NAV } from '../nav.js'

export function SiteNav() {
  return (
    <nav className="site-nav" aria-label="Site sections">
      <ul className="site-nav-list">
        {SITE_NAV.map((item) => (
          <li key={item.path}>
            <NavLink
              to={item.path}
              end={item.end}
              className={({ isActive }) =>
                isActive ? 'site-nav-link site-nav-link-active' : 'site-nav-link'
              }
            >
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
