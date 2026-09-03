import { Route, Routes } from 'react-router-dom'

import ScaffoldCheck from './pages/ScaffoldCheck.jsx'

/**
 * Route table. Real screens (login, report list, report detail, dashboard, alerts) get
 * added here as they are built; ScaffoldCheck exists only to prove the frontend can reach
 * the API and will be replaced by the dashboard.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ScaffoldCheck />} />
    </Routes>
  )
}
