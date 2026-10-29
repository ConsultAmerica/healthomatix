"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentProps,
  type ReactNode,
} from "react";
import { Icon, type IconName } from "@/components/icons";
import type { ApiProblem, QueryState } from "@/lib/api";

/* ——— Layout ——— */

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1 id="page-title">{title}</h1>
        {description && <p className="lead">{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section className="app-section" aria-labelledby={id}>
      <div className="app-section-heading">
        <div>
          <h2 id={id}>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {actions && <div className="app-section-actions">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

export function Card({
  children,
  className = "",
  padding = "default",
}: {
  children: ReactNode;
  className?: string;
  padding?: "default" | "compact" | "none";
}) {
  return <div className={`app-card app-card-${padding} ${className}`.trim()}>{children}</div>;
}

export function Breadcrumbs({
  items,
}: {
  items: Array<{ label: string; href?: string }>;
}) {
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <ol>
        {items.map((item, index) => {
          const last = index === items.length - 1;
          return (
            <li key={`${item.label}-${index}`}>
              {item.href && !last ? <Link href={item.href}>{item.label}</Link> : <span aria-current={last ? "page" : undefined}>{item.label}</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function SearchField({
  label = "Search",
  value,
  onChange,
  placeholder = "Search…",
  id,
}: {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  id?: string;
}) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <div className="search-field">
      <label className="visually-hidden" htmlFor={fieldId}>
        {label}
      </label>
      <span className="search-field-icon" aria-hidden="true">
        <Icon name="file" size={16} />
      </span>
      <input
        id={fieldId}
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="off"
      />
    </div>
  );
}

export function DashboardGrid({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`dashboard-grid ${className}`.trim()}>{children}</div>;
}

export function Skeleton({ className = "", width }: { className?: string; width?: string }) {
  return <span className={`skeleton-block ${className}`.trim()} style={width ? { width } : undefined} aria-hidden="true" />;
}

export function StatTile({
  label,
  value,
  hint,
  href,
  icon,
  attention = false,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  href?: string;
  icon?: IconName;
  /** Highlights the tile when the value needs action (for example, items awaiting review). */
  attention?: boolean;
}) {
  const body = (
    <>
      <span className="stat-top">
        <span className="stat-label">{label}</span>
        {icon && (
          <span className="stat-icon">
            <Icon name={icon} size={17} />
          </span>
        )}
      </span>
      <strong className="stat-value">{value}</strong>
      {hint && <span className="stat-hint">{hint}</span>}
      {href && (
        <span className="stat-more">
          View <Icon name="arrowRight" size={14} />
        </span>
      )}
    </>
  );
  const className = `stat-tile${href ? " stat-tile-link" : ""}${attention ? " stat-attention" : ""}`;
  return href ? (
    <Link className={className} href={href}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}

/* ——— Status ——— */

export type Tone = "neutral" | "success" | "info" | "warning" | "danger";

const toneByStatus: Record<string, Tone> = {
  active: "success",
  booked: "success",
  verified: "success",
  accepted: "success",
  granted: "success",
  available: "success",
  open: "info",
  pending: "warning",
  invited: "warning",
  processing: "info",
  cancelled: "neutral",
  rescheduled: "neutral",
  expired: "neutral",
  withdrawn: "neutral",
  inactive: "neutral",
  revoked: "danger",
  rejected: "danger",
  suspended: "danger",
};

export function toneFor(status: string): Tone {
  return toneByStatus[status.toLowerCase()] ?? "neutral";
}

export function humanize(value: string): string {
  const text = value.replaceAll("_", " ").replaceAll("-", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function StatusBadge({ status, tone, children }: { status?: string; tone?: Tone; children?: ReactNode }) {
  const resolved = tone ?? (status ? toneFor(status) : "neutral");
  return (
    <span className={`badge badge-${resolved}`}>
      <span className="badge-dot" aria-hidden="true" />
      {children ?? (status ? humanize(status) : null)}
    </span>
  );
}

/* ——— Feedback states ——— */

export function LoadingState({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <span className="visually-hidden">{label}…</span>
      {Array.from({ length: rows }, (_, index) => (
        <span className="skeleton-row" key={index} aria-hidden="true" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  children,
  action,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="state-panel state-empty">
      <span className="state-icon" aria-hidden="true">○</span>
      <div>
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
        {children && <p>{children}</p>}
        {action && <div className="state-actions">{action}</div>}
      </div>
    </div>
  );
}

const problemCopy: Record<ApiProblem["kind"], { title: string; icon: string }> = {
  unauthenticated: { title: "Sign in to continue", icon: "→" },
  forbidden: { title: "You don't have access to this", icon: "⊘" },
  "not-found": { title: "Not available", icon: "?" },
  conflict: { title: "This changed since you last looked", icon: "↻" },
  gone: { title: "This is no longer available", icon: "⌛" },
  invalid: { title: "Some details need attention", icon: "!" },
  unavailable: { title: "Temporarily unavailable", icon: "!" },
  offline: { title: "You're offline", icon: "⇣" },
  unexpected: { title: "Something went wrong", icon: "!" },
};

export function ProblemState({
  problem,
  onRetry,
  compact = false,
}: {
  problem: ApiProblem;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const copy = problemCopy[problem.kind];
  const canRetry = onRetry && ["unavailable", "offline", "unexpected", "conflict"].includes(problem.kind);
  const pathname = usePathname();
  const returnTo = pathname || "/";
  return (
    <div className={`state-panel state-problem state-${problem.kind}${compact ? " state-compact" : ""}`} role="alert">
      <span className="state-icon" aria-hidden="true">{copy.icon}</span>
      <div>
        <h3>{copy.title}</h3>
        <p>{problem.message}</p>
        {problem.requestId && <p className="state-reference">Reference: {problem.requestId}</p>}
        <div className="state-actions">
          {problem.kind === "unauthenticated" && (
            <a className="button button-small" href={`/auth/login?returnTo=${encodeURIComponent(returnTo)}`}>
              Sign in
            </a>
          )}
          {canRetry && (
            <button className="button button-light button-small" type="button" onClick={onRetry}>
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function QueryView<T>({
  state,
  onRetry,
  loadingLabel,
  rows,
  children,
}: {
  state: QueryState<T>;
  onRetry?: () => void;
  loadingLabel?: string;
  rows?: number;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "idle" || state.status === "loading") {
    return <LoadingState label={loadingLabel} rows={rows} />;
  }
  if (state.status === "error") {
    return <ProblemState problem={state.problem} onRetry={onRetry} />;
  }
  return <div aria-busy={state.refreshing}>{children(state.data)}</div>;
}

export function Notice({ title, children, tone = "info" }: { title: string; children?: ReactNode; tone?: Tone }) {
  return (
    <div className={`inline-notice inline-notice-${tone}`} role="note">
      <span className="inline-notice-mark" aria-hidden="true">i</span>
      <div>
        <strong>{title}</strong>
        {children && <p>{children}</p>}
      </div>
    </div>
  );
}

/* ——— Forms ——— */

type FieldProps = {
  label: string;
  hint?: ReactNode;
  error?: string;
};

export function TextField({ label, hint, error, id, ...input }: FieldProps & ComponentProps<"input">) {
  const generated = useId();
  const fieldId = id ?? generated;
  const describedBy = [hint ? `${fieldId}-hint` : "", error ? `${fieldId}-error` : ""].filter(Boolean).join(" ");
  return (
    <div className={`field${error ? " field-invalid" : ""}`}>
      <label htmlFor={fieldId}>
        {label}
        {input.required && <span className="field-required" aria-hidden="true"> *</span>}
      </label>
      <input id={fieldId} aria-invalid={Boolean(error) || undefined} aria-describedby={describedBy || undefined} {...input} />
      {hint && <p className="field-hint" id={`${fieldId}-hint`}>{hint}</p>}
      {error && <p className="field-error" id={`${fieldId}-error`}>{error}</p>}
    </div>
  );
}

export function SelectField({
  label,
  hint,
  error,
  id,
  children,
  ...select
}: FieldProps & ComponentProps<"select">) {
  const generated = useId();
  const fieldId = id ?? generated;
  const describedBy = [hint ? `${fieldId}-hint` : "", error ? `${fieldId}-error` : ""].filter(Boolean).join(" ");
  return (
    <div className={`field${error ? " field-invalid" : ""}`}>
      <label htmlFor={fieldId}>
        {label}
        {select.required && <span className="field-required" aria-hidden="true"> *</span>}
      </label>
      <select id={fieldId} aria-invalid={Boolean(error) || undefined} aria-describedby={describedBy || undefined} {...select}>
        {children}
      </select>
      {hint && <p className="field-hint" id={`${fieldId}-hint`}>{hint}</p>}
      {error && <p className="field-error" id={`${fieldId}-error`}>{error}</p>}
    </div>
  );
}

export function FormError({ problem }: { problem: ApiProblem | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (problem) ref.current?.focus();
  }, [problem]);
  if (!problem) return null;
  const fieldMessages = Object.entries(problem.fields);
  return (
    <div className="form-error" role="alert" tabIndex={-1} ref={ref}>
      <strong>{problemCopy[problem.kind].title}</strong>
      <p>{problem.message}</p>
      {fieldMessages.length > 0 && (
        <ul>
          {fieldMessages.map(([field, message]) => (
            <li key={field}>
              {humanize(field)}: {message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SubmitButton({
  pending,
  children,
  pendingLabel = "Saving…",
  className = "button button-small",
  ...button
}: { pending: boolean; pendingLabel?: string } & ComponentProps<"button">) {
  return (
    <button className={className} type="submit" disabled={pending || button.disabled} aria-busy={pending} {...button}>
      {pending ? pendingLabel : children}
    </button>
  );
}

/* ——— Dialog ——— */

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <dialog
      ref={ref}
      className="app-dialog"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="app-dialog-body">
        <div className="app-dialog-header">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close dialog">
            ×
          </button>
        </div>
        {description && <p className="app-dialog-description">{description}</p>}
        {open && children}
      </div>
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  pending = false,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  pending?: boolean;
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title} description={description}>
      <div className="dialog-actions">
        <button className="button button-light button-small" type="button" onClick={onClose} disabled={pending}>
          {cancelLabel}
        </button>
        <button
          className={`button button-small${danger ? " button-danger" : ""}`}
          type="button"
          onClick={onConfirm}
          disabled={pending}
          aria-busy={pending}
        >
          {pending ? "Working…" : confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}

/* ——— Toasts ——— */

type Toast = { id: number; message: string; tone: Tone };
const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback((message: string, tone: Tone = "success") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), 5000);
  }, []);
  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div className={`toast toast-${toast.tone}`} key={toast.id}>
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

/* ——— Misc ——— */

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="button button-light button-small"
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 2000);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}

export function Table({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label={caption}>
      <table className="data-table">
        <caption className="visually-hidden">{caption}</caption>
        {children}
      </table>
    </div>
  );
}
