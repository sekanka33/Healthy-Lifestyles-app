import { CheckCircle2, KeyRound, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Badge, Button, Card, PageHeader } from '../components/ui';
import { Field, FormError } from '../components/ui/Field';
import { ApiError } from '../lib/api';
import { useAuth, type AdminMe } from '../lib/auth';
import { validateCode } from './LoginPage';

const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong. Please try again.');

function MfaCard() {
  const { admin, request, setAdmin } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [codeError, setCodeError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!admin) return null;

  const start = async () => {
    setBusy(true); setError(null);
    try { setSetup(await request('/auth/mfa/setup', { method: 'POST' })); } catch (e) { setError(errText(e)); } finally { setBusy(false); }
  };

  const confirm = async (e: FormEvent) => {
    e.preventDefault();
    const problem = validateCode(code);
    setCodeError(problem); setError(null);
    if (problem) return;
    setBusy(true);
    try {
      setAdmin(await request<AdminMe>('/auth/mfa/enable', { method: 'POST', body: { code: code.replace(/\s/g, '') } }));
      setSetup(null); setCode('');
    } catch (err) { setError(errText(err)); } finally { setBusy(false); }
  };

  const disable = async (e: FormEvent) => {
    e.preventDefault();
    const problem = validateCode(code);
    setCodeError(problem); setError(null);
    if (problem || !password) { if (!password) setError('Enter your password.'); return; }
    setBusy(true);
    try {
      setAdmin(await request<AdminMe>('/auth/mfa/disable', { method: 'POST', body: { password, code: code.replace(/\s/g, '') } }));
      setCode(''); setPassword('');
    } catch (err) { setError(errText(err)); } finally { setBusy(false); }
  };

  return (
    <Card
      title="Two-step verification"
      subtitle="A code from an authenticator app is needed at every sign-in."
      actions={admin.mfa_enabled ? <Badge tone="brand">On</Badge> : <Badge tone={admin.mfa_required ? 'bad' : 'warn'}>Off</Badge>}
    >
      {admin.mfa_setup_needed && (
        <p className="mb-4 flex items-start gap-2 rounded-lg bg-warn-bg px-3 py-2 text-sm text-warn" role="status">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          Two-step verification is required on this server. Set it up to use the dashboard.
        </p>
      )}

      {admin.mfa_enabled ? (
        admin.mfa_required ? (
          <p className="flex items-center gap-2 text-sm text-ink-700"><CheckCircle2 className="size-4 text-brand-600" aria-hidden /> Protected. It can't be turned off on this server.</p>
        ) : (
          <form onSubmit={disable} noValidate className="max-w-sm space-y-4">
            <p className="text-sm text-ink-700">To turn it off, confirm your password and a current code.</p>
            <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={setPassword} />
            <Field label="Verification code" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={setCode} error={codeError} maxLength={7} />
            <FormError message={error} />
            <Button type="submit" variant="secondary" loading={busy}>Turn off</Button>
          </form>
        )
      ) : !setup ? (
        <>
          <FormError message={error} />
          <Button icon={ShieldCheck} onClick={start} loading={busy} className="mt-1">Set up two-step verification</Button>
        </>
      ) : (
        <form onSubmit={confirm} noValidate className="max-w-lg space-y-4">
          <ol className="list-decimal space-y-2 pl-5 text-sm text-ink-700">
            <li>Open your authenticator app (Google Authenticator, 1Password, Microsoft Authenticator…) and add an account manually.</li>
            <li>Enter this key. It's shown only now. Time-based, 6 digits.</li>
          </ol>
          <code data-testid="mfa-secret" className="block break-all rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-sm tracking-wider">
            {setup.secret.match(/.{1,4}/g)?.join(' ')}
          </code>
          <details className="text-xs text-ink-500">
            <summary className="cursor-pointer">Setup link (for apps that accept otpauth:// links)</summary>
            <p className="mt-1 break-all font-mono">{setup.otpauth_uri}</p>
          </details>
          <Field label="Code from the app" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={setCode} error={codeError} maxLength={7} />
          <FormError message={error} />
          <div className="flex gap-2">
            <Button type="submit" loading={busy}>Turn on</Button>
            <Button variant="ghost" onClick={() => { setSetup(null); setCode(''); }}>Cancel</Button>
          </div>
        </form>
      )}
    </Card>
  );
}

export function validatePasswordChange(current: string, next: string, confirm: string): string | null {
  if (!current) return 'Enter your current password.';
  if (next.length < 12) return 'The new password must be at least 12 characters.';
  if (next !== confirm) return "The new passwords don't match.";
  if (next === current) return 'Choose a password different from the current one.';
  return null;
}

function PasswordCard() {
  const { request, applySession } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = validatePasswordChange(current, next, confirm);
    setError(problem); setDone(false);
    if (problem) return;
    setBusy(true);
    try {
      applySession(await request('/auth/change-password', { method: 'POST', body: { current_password: current, new_password: next } }));
      setCurrent(''); setNext(''); setConfirm(''); setDone(true);
    } catch (err) { setError(errText(err)); } finally { setBusy(false); }
  };

  return (
    <Card title="Password" subtitle="Changing it signs you out everywhere else.">
      <form onSubmit={submit} noValidate className="max-w-sm space-y-4">
        <Field label="Current password" type="password" autoComplete="current-password" value={current} onChange={setCurrent} />
        <Field label="New password" type="password" autoComplete="new-password" value={next} onChange={setNext} hint="At least 12 characters." />
        <Field label="Confirm new password" type="password" autoComplete="new-password" value={confirm} onChange={setConfirm} />
        <FormError message={error} />
        {done && <p role="status" className="text-sm text-brand-700">Password changed.</p>}
        <Button type="submit" icon={KeyRound} loading={busy}>Change password</Button>
      </form>
    </Card>
  );
}

export function SecurityPage() {
  const { admin } = useAuth();
  return (
    <>
      <PageHeader title="Security" description={admin ? `${admin.email} · ${admin.role_label}` : undefined} />
      <div className="grid gap-6 lg:grid-cols-2">
        <MfaCard />
        <PasswordCard />
      </div>
    </>
  );
}
