import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../lib/auth'

export function LoginPage() {
  const [name, setName] = useState('Ahsan Khan')
  const [email, setEmail] = useState('ahsan@propertylead.local')
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    login({ name, email, role: 'admin' })
    navigate('/admin')
  }

  return (
    <div className="w-full max-w-md">
      <h2 className="text-2xl font-semibold text-white">Sign in to the ops console</h2>
      <p className="mt-2 text-sm text-slate-400">Choose a role to view the dashboard tailored to your workflow.</p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <label className="block text-sm text-slate-300">
          <span className="mb-1 block">Name</span>
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none"
          />
        </label>

        <label className="block text-sm text-slate-300">
          <span className="mb-1 block">Email</span>
          <input
            required
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none"
          />
        </label>

        <button className="w-full rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-400">
          Enter dashboard
        </button>
      </form>
    </div>
  )
}
