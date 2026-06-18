/** Shared admin navigation (all protected pages except mentor reply). */
export const SITE_NAV = [
  { path: '/', label: 'Home', end: true },
  { path: '/seasons', label: 'Seasons' },
  { path: '/practices', label: 'Practices' },
  { path: '/attendance', label: 'Attendance' },
  { path: '/coaches', label: 'Coaches' },
  { path: '/tfk-staff', label: 'TFK Staff' },
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
    path: '/attendance',
    title: 'Attendance',
    description:
      'Record which assigned mentors attended or missed a practice; add general comments.',
  },
  {
    path: '/coaches',
    title: 'Coaches',
    description: 'Manage coaches and their season assignment.',
  },
  {
    path: '/tfk-staff',
    title: 'TFK Staff',
    description: 'Manage TFK staff contacts with name, email, and cell phone.',
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
