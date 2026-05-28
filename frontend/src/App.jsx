import { Route, Routes } from 'react-router-dom'

import CoachesPage from './pages/CoachesPage.jsx'
import EmailsPage from './pages/EmailsPage.jsx'
import HomePage from './pages/HomePage.jsx'
import MentorReplyPage from './pages/MentorReplyPage.jsx'
import MentorsPage from './pages/MentorsPage.jsx'
import PracticeDetailPage from './pages/PracticeDetailPage.jsx'
import PracticesPage from './pages/PracticesPage.jsx'
import SeasonsPage from './pages/SeasonsPage.jsx'

import './App.css'

export default function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/seasons" element={<SeasonsPage />} />
        <Route path="/practices" element={<PracticesPage />} />
        <Route path="/practices/:id" element={<PracticeDetailPage />} />
        <Route path="/coaches" element={<CoachesPage />} />
        <Route path="/mentors" element={<MentorsPage />} />
        <Route path="/emails" element={<EmailsPage />} />
        <Route path="/mentor-reply/:token" element={<MentorReplyPage />} />
      </Routes>
    </div>
  )
}
