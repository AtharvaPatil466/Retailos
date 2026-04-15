import { useState } from 'react';

export default function LoginForm({ onSuccess }) {
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (mode === 'register') {
        const res = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username,
            email: email || `${username}@retailos.local`,
            password,
            full_name: fullName || username,
            role: 'owner',
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          // If user exists, switch to login
          if (res.status === 400 && data.detail?.includes('already')) {
            setMode('login');
            setError('Account exists. Please log in.');
            setLoading(false);
            return;
          }
          throw new Error(data.detail || 'Registration failed');
        }
        localStorage.setItem('retailos_token', data.access_token);
        localStorage.setItem('token', data.access_token);
        onSuccess();
      } else {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Login failed');
        }
        localStorage.setItem('retailos_token', data.access_token);
        localStorage.setItem('token', data.access_token);
        onSuccess();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mb-8 rounded-[28px] border border-amber-200 bg-[rgba(255,252,247,0.86)] p-6 shadow-[0_20px_55px_rgba(0,0,0,0.06)]">
      <div className="text-[10px] font-black uppercase tracking-[0.22em] text-amber-700">
        Authentication Required
      </div>
      <h2 className="font-display mt-3 text-2xl font-bold tracking-tight text-stone-900">
        {mode === 'login' ? 'Sign in to RetailOS' : 'Create your account'}
      </h2>
      <form onSubmit={handleSubmit} className="mt-4 max-w-sm space-y-3">
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          className="w-full rounded-xl border border-stone-300 bg-white px-4 py-2.5 text-sm text-stone-900 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
        />
        {mode === 'register' && (
          <>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-stone-300 bg-white px-4 py-2.5 text-sm text-stone-900 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
            />
            <input
              type="text"
              placeholder="Full Name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-xl border border-stone-300 bg-white px-4 py-2.5 text-sm text-stone-900 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
            />
          </>
        )}
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="w-full rounded-xl border border-stone-300 bg-white px-4 py-2.5 text-sm text-stone-900 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
        />
        {error && <p className="text-xs text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-xl bg-stone-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-stone-800 disabled:opacity-50"
        >
          {loading ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Create Account'}
        </button>
        <button
          type="button"
          onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
          className="w-full text-center text-xs text-stone-500 hover:text-stone-700"
        >
          {mode === 'login' ? "Don't have an account? Register" : 'Already have an account? Sign in'}
        </button>
      </form>
    </div>
  );
}
