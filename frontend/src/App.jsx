import { Route, Routes } from 'react-router-dom'

import { PasswordGate } from './components/PasswordGate.jsx'
import AttendancePage from './pages/AttendancePage.jsx'
import CoachesPage from './pages/CoachesPage.jsx'
import EmailsPage from './pages/EmailsPage.jsx'
import EmailDetailPage from './pages/EmailDetailPage.jsx'
import PracticeReminderDetailPage from './pages/PracticeReminderDetailPage.jsx'
import HomePage from './pages/HomePage.jsx'
import MentorReplyPage from './pages/MentorReplyPage.jsx'
import MentorDetailPage from './pages/MentorDetailPage.jsx'
import MentorsPage from './pages/MentorsPage.jsx'
import PracticeDetailPage from './pages/PracticeDetailPage.jsx'
import PracticesPage from './pages/PracticesPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import SeasonsPage from './pages/SeasonsPage.jsx'
import TfkStaffPage from './pages/TfkStaffPage.jsx'

import './App.css'

function Protected({ children }) {
  return <PasswordGate>{children}</PasswordGate>
}

export default function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/mentor-reply" element={<MentorReplyPage />} />
        <Route path="/mentor-reply/:token" element={<MentorReplyPage />} />
        <Route
          path="/"
          element={
            <Protected>
              <HomePage />
            </Protected>
          }
        />
        <Route
          path="/seasons"
          element={
            <Protected>
              <SeasonsPage />
            </Protected>
          }
        />
        <Route
          path="/practices"
          element={
            <Protected>
              <PracticesPage />
            </Protected>
          }
        />
        <Route
          path="/practices/:id"
          element={
            <Protected>
              <PracticeDetailPage />
            </Protected>
          }
        />
        <Route
          path="/attendance"
          element={
            <Protected>
              <AttendancePage />
            </Protected>
          }
        />
        <Route
          path="/attendance/:id"
          element={
            <Protected>
              <AttendancePage />
            </Protected>
          }
        />
        <Route
          path="/coaches"
          element={
            <Protected>
              <CoachesPage />
            </Protected>
          }
        />
        <Route
          path="/tfk-staff"
          element={
            <Protected>
              <TfkStaffPage />
            </Protected>
          }
        />
        <Route
          path="/mentors/:id"
          element={
            <Protected>
              <MentorDetailPage />
            </Protected>
          }
        />
        <Route
          path="/mentors"
          element={
            <Protected>
              <MentorsPage />
            </Protected>
          }
        />
        <Route
          path="/emails"
          element={
            <Protected>
              <EmailsPage />
            </Protected>
          }
        />
        <Route
          path="/emails/practice-reminder/:id"
          element={
            <Protected>
              <PracticeReminderDetailPage />
            </Protected>
          }
        />
        <Route
          path="/emails/:id"
          element={
            <Protected>
              <EmailDetailPage />
            </Protected>
          }
        />
        <Route
          path="/reports"
          element={
            <Protected>
              <ReportsPage />
            </Protected>
          }
        />
      </Routes>
    </div>
  )
}
