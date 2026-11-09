import { ArrowLeft, Info, ShieldCheck } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useLocation } from 'react-router';
import { Logo } from '../components/layout/Logo';
import { Button } from '../components/ui';
import { Field, FormError } from '../components/ui/Field';
import { ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateLogin(email: string, password: string): { email?: string; password?: string } {
  const errors: { email?: string; password?: string } = {};
  if (!email.trim()) errors.email = 'Enter your email address.';
  else if (!EMAIL_RE.test(email.trim())) errors.email = 'Enter a valid email address.';
  if (!password) errors.password = 'Enter your password.';
  return errors;
}

export function validateCode(code: string): string | null {
  return /^\d{6}$/.test(code.replace(/\s/g, '')) ? null : 'Enter the 6-digit code from your authenticator app.';
}

function message(e: unknown): string {
  if (e instanceof ApiError) return e.status === 429 ? 'Too many attempts. Please wait a few minutes and try again.' : e.message;
  return 'Something went wrong. Please try again.';
}

export function LoginPage() {
  const { status, login, verifyMfa, notice } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string; code?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === 'signed_in') {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from !== '/login' ? from : '/'} replace />;
  }

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault();
    const errs = validateLogin(email, password);
    setFieldErrors(errs);
    setError(null);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const res = await login(email.trim(), password);
      if (res.kind === 'mfa') { setMfaToken(res.mfaToken); setPassword(''); }
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (e: FormEvent) => {
    e.preventDefault();
    const problem = validateCode(code);
    setFieldErrors(problem ? { code: problem } : {});
    setError(null);
    if (problem || !mfaToken) return;
    setBusy(true);
    try {
      await verifyMfa(mfaToken, code.replace(/\s/g, ''));
    } catch (err) {
      if (err instanceof ApiError && err.code === 'mfa_challenge_expired') { setMfaToken(null); setCode(''); }
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-canvas px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center"><Logo /></div>
        <div className="rounded-[var(--radius-card)] border border-line bg-surface p-6 shadow-card sm:p-8">
          {notice && !mfaToken && (
            <p className="mb-5 flex items-start gap-2 rounded-lg bg-info-bg px-3 py-2 text-sm text-info" role="status">
              <Info className="mt-0.5 size-4 shrink-0" aria-hidden /> {notice}
            </p>
          )}

          {!mfaToken ? (
            <form onSubmit={submitPassword} noValidate>
              <h1 className="text-lg font-semibold text-ink-900">Sign in</h1>
              <p className="mt-1 text-sm text-ink-500">LifePulse administration. Authorised staff only.</p>
              <div className="mt-6 space-y-4">
                <Field label="Email" type="email" autoComplete="username" value={email} onChange={setEmail} error={fieldErrors.email} autoFocus />
                <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={setPassword} error={fieldErrors.password} />
              </div>
              <FormError message={error} />
              <Button type="submit" loading={busy} className="mt-6 w-full">Sign in</Button>
            </form>
          ) : (
            <form onSubmit={submitCode} noValidate>
              <span className="grid size-10 place-items-center rounded-full bg-brand-50 text-brand-700"><ShieldCheck className="size-5" aria-hidden /></span>
              <h1 className="mt-4 text-lg font-semibold text-ink-900">Two-step verification</h1>
              <p className="mt-1 text-sm text-ink-500">Enter the 6-digit code from your authenticator app.</p>
              <div className="mt-6">
                <Field label="Verification code" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={setCode}
                  error={fieldErrors.code} maxLength={7} autoFocus />
              </div>
              <FormError message={error} />
              <Button type="submit" loading={busy} className="mt-6 w-full">Verify</Button>
              <button type="button" onClick={() => { setMfaToken(null); setCode(''); setError(null); }}
                className="mt-3 inline-flex w-full items-center justify-center gap-1.5 text-sm text-ink-500 hover:text-ink-900">
                <ArrowLeft className="size-4" aria-hidden /> Use a different account
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
