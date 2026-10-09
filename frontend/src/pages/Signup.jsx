import { Link, Navigate, useNavigate } from 'react-router-dom'
import AuthForm from '../components/AuthForm'
import { useAuth } from '../lib/auth'

export default function Signup() {
  const { user, signup } = useAuth()
  const navigate = useNavigate()
  if (user) return <Navigate to="/" replace />

  return (
    <AuthForm
      title="Create your account"
      submitLabel="Sign up"
      fields={[
        { name: 'name', label: 'Name', type: 'text', autoComplete: 'name' },
        { name: 'email', label: 'Email', type: 'email', autoComplete: 'email' },
        {
          name: 'password',
          label: 'Password (8+ characters)',
          type: 'password',
          autoComplete: 'new-password',
          minLength: 8,
        },
      ]}
      onSubmit={async ({ name, email, password }) => {
        await signup(name, email, password)
        navigate('/', { replace: true })
      }}
      footer={
        <>
          Already have an account? <Link to="/login" className="font-semibold text-brand-700 hover:underline">Log in</Link>
        </>
      }
    />
  )
}
