import { lazy, Suspense } from 'react'
import { Outlet, Route, Routes } from 'react-router-dom'

import { PasswordGate } from './components/PasswordGate.jsx'

import './App.css'

const AttendancePage = lazy(() => import('./pages/AttendancePage.tsx'))
const CoachesPage = lazy(() => import('./pages/CoachesPage.tsx'))
const EmailsPage = lazy(() => import('./pages/EmailsPage.jsx'))
const EmailDetailPage = lazy(() => import('./pages/EmailDetailPage.jsx'))
const PracticeReminderDetailPage = lazy(
  () => import('./pages/PracticeReminderDetailPage.jsx')
)
const HomePage = lazy(() => import('./pages/HomePage.tsx'))
const MentorReplyPage = lazy(() => import('./pages/MentorReplyPage.jsx'))
const MentorCellPhonePage = lazy(() => import('./pages/MentorCellPhonePage.jsx'))
const PublicMentorDirectoryPage = lazy(
  () => import('./pages/PublicMentorDirectoryPage.jsx')
)
const MentorSwapApprovePage = lazy(() => import('./pages/MentorSwapApprovePage.jsx'))
const MentorSwapRejectPage = lazy(() => import('./pages/MentorSwapRejectPage.jsx'))
const MentorDetailPage = lazy(() => import('./pages/MentorDetailPage.jsx'))
const MentorsPage = lazy(() => import('./pages/MentorsPage.jsx'))
const PracticeDetailPage = lazy(() => import('./pages/PracticeDetailPage.jsx'))
const PracticesPage = lazy(() => import('./pages/PracticesPage.jsx'))
const ReportsPage = lazy(() => import('./pages/ReportsPage.jsx'))
const SeasonsPage = lazy(() => import('./pages/SeasonsPage.tsx'))
const TfkStaffPage = lazy(() => import('./pages/TfkStaffPage.tsx'))

function PageFallback() {
  return <p className="muted">Loading…</p>
}

function ProtectedLayout() {
  return (
    <PasswordGate>
      <Outlet />
    </PasswordGate>
  )
}

export default function App() {
  return (
    <div className="app">
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/mentor-reply" element={<MentorReplyPage />} />
          <Route path="/mentor-reply/:token" element={<MentorReplyPage />} />
          <Route path="/mentor-cell-phone" element={<MentorCellPhonePage />} />
          <Route
            path="/mentor-cell-phone/:token"
            element={<MentorCellPhonePage />}
          />
          <Route
            path="/mentor-directory/:tab?"
            element={<PublicMentorDirectoryPage />}
          />
          <Route
            path="/mentor-swap/approve/:token"
            element={<MentorSwapApprovePage />}
          />
          <Route
            path="/mentor-swap/reject/:token"
            element={<MentorSwapRejectPage />}
          />
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/seasons" element={<SeasonsPage />} />
            <Route path="/practices" element={<PracticesPage />} />
            <Route path="/practices/:id" element={<PracticeDetailPage />} />
            <Route path="/attendance" element={<AttendancePage />} />
            <Route path="/attendance/:id" element={<AttendancePage />} />
            <Route path="/coaches" element={<CoachesPage />} />
            <Route path="/tfk-staff" element={<TfkStaffPage />} />
            <Route path="/mentors/:id" element={<MentorDetailPage />} />
            <Route path="/mentors" element={<MentorsPage />} />
            <Route path="/emails" element={<EmailsPage />} />
            <Route
              path="/emails/practice-reminder/:id"
              element={<PracticeReminderDetailPage />}
            />
            <Route path="/emails/:id" element={<EmailDetailPage />} />
            <Route path="/reports" element={<ReportsPage />} />
          </Route>
        </Routes>
      </Suspense>
    </div>
  )
}
