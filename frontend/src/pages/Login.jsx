import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import AuthForm from '../components/AuthForm'
import { useAuth } from '../lib/auth'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const from = useLocation().state?.from || '/'
  if (user) return <Navigate to={from} replace />

  return (
    <AuthForm
      title="Log in"
      submitLabel="Log in"
      fields={[
        { name: 'email', label: 'Email', type: 'email', autoComplete: 'email' },
        { name: 'password', label: 'Password', type: 'password', autoComplete: 'current-password' },
      ]}
      onSubmit={async ({ email, password }) => {
        await login(email, password)
        navigate(from, { replace: true })
      }}
      footer={
        <>
          New here? <Link to="/signup" className="font-semibold text-brand-700 hover:underline">Create an account</Link>
          <span className="mt-2 block">
            Or{' '}
            <Link to="/decode" className="font-semibold text-brand-700 hover:underline">
              decode a job description free
            </Link>
            , no account needed.
          </span>
        </>
      }
    />
  )
}
