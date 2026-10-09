import { Navigate, Route, Routes } from 'react-router-dom'
import ComingSoon from './components/ComingSoon'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Signup from './pages/Signup'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="setup" element={<ComingSoon title="New interview" phase={2} />} />
        <Route path="interview/:id" element={<ComingSoon title="Interview" phase={2} />} />
        <Route path="report/:id" element={<ComingSoon title="Report" phase={4} />} />
        <Route path="stories" element={<ComingSoon title="Story bank" phase={7} />} />
        <Route path="decoder" element={<ComingSoon title="JD decoder" phase={8} />} />
        <Route path="debrief" element={<ComingSoon title="Debrief" phase={8} />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
