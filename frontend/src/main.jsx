import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { TimezoneProvider } from './components/TimezoneProvider.jsx'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <TimezoneProvider>
        <App />
      </TimezoneProvider>
    </BrowserRouter>
  </StrictMode>,
)
