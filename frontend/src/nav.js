/** Shared admin navigation (all protected pages except mentor reply). */
export const SITE_NAV = [
  { path: '/', label: 'Home', end: true },
  { path: '/seasons', label: 'Seasons' },
  { path: '/practices', label: 'Practices' },
  { path: '/coaches', label: 'Coaches' },
  { path: '/mentors', label: 'Mentors' },
  { path: '/emails', label: 'Emails' },
  { path: '/reports', label: 'Reports' },
]

export const SITE_PAGE_CARDS = [
  {
    path: '/seasons',
    title: 'Seasons',
    description: 'View, create, edit, and delete seasons.',
  },
  {
    path: '/practices',
    title: 'Practices',
    description: 'List practices, filter by season, add, edit, or remove.',
  },
  {
    path: '/coaches',
    title: 'Coaches',
    description: 'Manage coaches and their season assignment.',
  },
  {
    path: '/mentors',
    title: 'Mentors',
    description: 'Manage mentors with season, type, and pace assignments.',
  },
  {
    path: '/emails',
    title: 'Emails',
    description:
      'Schedule mentor emails with practices; view upcoming and completed sends.',
  },
  {
    path: '/reports',
    title: 'Reports',
    description:
      'View practice rosters with coaches and mentors; sort and download Excel.',
  },
]
