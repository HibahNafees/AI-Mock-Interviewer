import { Navigate, Route, Routes } from 'react-router-dom'
import ComingSoon from './components/ComingSoon'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Dashboard from './pages/Dashboard'
import Decoder from './pages/Decoder'
import Interview from './pages/Interview'
import Login from './pages/Login'
import Report from './pages/Report'
import Setup from './pages/Setup'
import Signup from './pages/Signup'
import Stories from './pages/Stories'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      {/* Public: the decoder works without an account and its results are shareable. */}
      <Route path="/decode" element={<Decoder standalone />} />
      <Route path="/decode/:token" element={<Decoder standalone />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="setup" element={<Setup />} />
        <Route path="interview/:id" element={<Interview />} />
        <Route path="report/:id" element={<Report />} />
        <Route path="stories" element={<Stories />} />
        <Route path="decoder" element={<Decoder />} />
        <Route path="decoder/:token" element={<Decoder />} />
        <Route path="debrief" element={<ComingSoon title="Debrief" phase={8} />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
