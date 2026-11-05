import { useState } from 'react';
import { login, register } from '../api';

const AuthDialog = ({ onClose }) => {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await (mode === 'login' ? login : register)(email, password);
      onClose();
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setBusy(false);
    }
  };

  const signingUp = mode === 'register';

  return (
    <div className="fixed inset-0 z-10 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm bg-white rounded-xl shadow-lg p-6 space-y-4"
      >
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{signingUp ? 'Create an account' : 'Sign in'}</h2>
          <p className="text-sm text-slate-500">Your files stay private and your questions are saved.</p>
        </div>
        <input
          type="email" required autoComplete="email" placeholder="Email" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
        />
        <input
          type="password" required placeholder="Password" value={password}
          minLength={signingUp ? 8 : undefined}
          autoComplete={signingUp ? 'new-password' : 'current-password'}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
        />
        {signingUp && <p className="text-xs text-slate-400">At least 8 characters.</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit" disabled={busy}
          className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 disabled:bg-slate-400"
        >
          {busy ? 'Please wait...' : signingUp ? 'Create account' : 'Sign in'}
        </button>
        <p className="text-sm text-slate-500 text-center">
          {signingUp ? 'Have an account?' : 'New here?'}{' '}
          <button
            type="button" className="text-blue-600 hover:underline"
            onClick={() => { setMode(signingUp ? 'login' : 'register'); setError(''); }}
          >
            {signingUp ? 'Sign in' : 'Create one'}
          </button>
        </p>
      </form>
    </div>
  );
};

export default AuthDialog;
