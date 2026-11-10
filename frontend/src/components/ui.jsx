import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Inbox, Loader2 } from "lucide-react";
import { classForStatus, normalizeStatus } from "../lib/format";

const STAT_TONES = {
  cyan: "text-cyan border-cyan/20 from-cyan/[0.06]",
  green: "text-normal border-normal/20 from-normal/[0.05]",
  amber: "text-suspicious border-suspicious/20 from-suspicious/[0.05]",
  red: "text-threat border-threat/20 from-threat/[0.05]",
  blue: "text-[#7fb4ff] border-electric/20 from-electric/[0.06]",
  neutral: "text-slate-200 border-line from-white/[0.02]",
};

export function Panel({ title, subtitle, action, children, className = "", bodyClassName = "", flush = false }) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && (
        <div className="panel-head">
          <div className="min-w-0">
            {title && <h2 className="text-[13px] font-semibold tracking-tight text-slate-100">{title}</h2>}
            {subtitle && <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">{subtitle}</p>}
          </div>
          {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
        </div>
      )}
      <div className={flush ? "" : `panel-body ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone = "cyan", icon: Icon, className = "" }) {
  const styles = STAT_TONES[tone] || STAT_TONES.cyan;
  return (
    <div className={`rounded-xl border bg-gradient-to-br to-transparent p-3.5 shadow-panel ${styles} ${className}`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] opacity-70">{label}</span>
        {Icon && <Icon size={14} className="opacity-60" />}
      </div>
      <div className="metric-value">{value ?? "—"}</div>
      {hint && <div className="mt-1 text-[10.5px] leading-snug text-slate-500">{hint}</div>}
    </div>
  );
}

export function Badge({ tone = "neutral", children, dot = false, className = "" }) {
  const tones = {
    neutral: "badge-neutral",
    cyan: "badge-cyan",
    green: "badge-green",
    amber: "badge-amber",
    red: "badge-red",
    blue: "badge-blue",
  };
  return (
    <span className={`badge ${tones[tone] || tones.neutral} ${className}`}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  return (
    <Badge tone={classForStatus(status)} dot>
      {normalizeStatus(status) || "UNKNOWN"}
    </Badge>
  );
}

export function Button({ variant = "primary", className = "", loading = false, children, ...props }) {
  const variants = { primary: "btn-primary", ghost: "btn-ghost", danger: "btn-danger" };
  return (
    <button className={`btn ${variants[variant] || variants.primary} ${className}`} disabled={loading || props.disabled} {...props}>
      {loading && <Loader2 size={13} className="animate-spin" />}
      {children}
    </button>
  );
}

export function LinkButton({ to, variant = "ghost", children, className = "" }) {
  const variants = { primary: "btn-primary", ghost: "btn-ghost", danger: "btn-danger" };
  return (
    <Link className={`btn ${variants[variant] || variants.ghost} ${className}`} to={to}>
      {children}
    </Link>
  );
}

export function Field({ label, hint, children, className = "", htmlFor }) {
  return (
    <label htmlFor={htmlFor} className={`block ${className}`}>
      <span className="label mb-1.5 block">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[10.5px] leading-relaxed text-slate-600">{hint}</span>}
    </label>
  );
}

export function Progress({ value = 0, message = "", tone = "cyan" }) {
  const palette = {
    cyan: "from-cyan to-electric",
    green: "from-normal to-cyan",
    red: "from-threat to-suspicious",
  };
  return (
    <div className="space-y-1.5">
      <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${palette[tone] || palette.cyan} transition-all duration-500`}
          style={{ width: `${Math.max(2, Math.min(100, Number(value) * 100))}%` }}
        />
      </div>
      <div className="flex justify-between gap-3 text-[10.5px] text-slate-500">
        <span className="truncate">{message || "Working…"}</span>
        <span className="font-mono">{Math.round((value || 0) * 100)}%</span>
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 rounded-xl border border-line bg-ink-900 p-3 text-slate-500">
        <Icon size={22} strokeWidth={1.6} />
      </div>
      <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
      {description && <p className="mt-1.5 max-w-md text-[11.5px] leading-relaxed text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorNotice({ error, onRetry, title = "Request failed" }) {
  if (!error) return null;
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-threat/25 bg-threat/[0.06] px-3.5 py-3">
      <div className="flex items-start gap-2.5">
        <AlertTriangle size={15} className="mt-0.5 shrink-0 text-threat" />
        <div>
          <p className="text-xs font-semibold text-threat/90">{title}</p>
          <p className="mt-0.5 text-[11px] leading-relaxed text-slate-400">{error.message || String(error)}</p>
        </div>
      </div>
      {onRetry && (
        <Button variant="ghost" onClick={onRetry} className="!py-1.5">
          Retry
        </Button>
      )}
    </div>
  );
}

export function DataTable({ columns, rows, rowKey = "id", empty = "No records yet.", dense = false, onRowClick }) {
  if (!rows?.length) {
    return <p className="px-1 py-6 text-center text-[11.5px] text-slate-600">{empty}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.align === "right" ? "text-right" : ""} style={column.width ? { width: column.width } : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={typeof rowKey === "function" ? rowKey(row) : row[rowKey] ?? index}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={onRowClick ? "cursor-pointer" : ""}
            >
              {columns.map((column) => (
                <td key={column.key} className={`${column.align === "right" ? "text-right" : ""} ${column.className || ""} ${dense ? "!py-2" : ""}`}>
                  {column.render ? column.render(row) : row[column.key] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ScopeNote({ children }) {
  return (
    <div className="scope-note">
      <span className="mt-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-cyan/80" />
      <span>{children}</span>
    </div>
  );
}

export function LoadingBlock({ rows = 3, className = "" }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton h-9 w-full" />
      ))}
    </div>
  );
}

export function SectionLabel({ children, action }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-3">
      <span className="eyebrow">{children}</span>
      {action}
    </div>
  );
}

export function KeyValue({ items, className = "" }) {
  return (
    <dl className={`space-y-2 ${className}`}>
      {items.filter(Boolean).map((item) => (
        <div key={item.label} className="flex items-start justify-between gap-3 border-b border-line/30 pb-1.5 last:border-0">
          <dt className="text-[10.5px] uppercase tracking-wide text-slate-500">{item.label}</dt>
          <dd className="text-right text-[11.5px] font-medium text-slate-200">{item.value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function MetricBar({ value, tone = "cyan", max = 1 }) {
  const palette = { cyan: "bg-cyan", green: "bg-normal", amber: "bg-suspicious", red: "bg-threat", blue: "bg-electric" };
  const width = Math.max(0, Math.min(100, ((Number(value) || 0) / max) * 100));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
      <div className={`h-full rounded-full ${palette[tone] || palette.cyan}`} style={{ width: `${width}%` }} />
    </div>
  );
}

export function ArrowLink({ to, children }) {
  return (
    <Link to={to} className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan/90 transition hover:text-cyan">
      {children}
      <ArrowRight size={12} />
    </Link>
  );
}
