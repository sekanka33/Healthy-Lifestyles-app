import { AlertCircle } from 'lucide-react';
import { useId, type InputHTMLAttributes } from 'react';
import { cx } from './index';

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> {
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  hint?: string;
}

export function Field({ label, value, onChange, error, hint, className, ...rest }: FieldProps) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-medium text-ink-700">{label}</label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={cx(
          'mt-1.5 block h-10 w-full rounded-lg border bg-surface px-3 text-sm text-ink-900 placeholder:text-ink-400',
          error ? 'border-bad-strong' : 'border-line focus:border-brand-500',
        )}
        {...rest}
      />
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-xs text-bad-strong">{error}</p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-ink-500">{hint}</p>
      ) : null}
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-4 flex items-start gap-2 rounded-lg bg-bad-bg px-3 py-2 text-sm text-bad-strong">
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden /> {message}
    </p>
  );
}
