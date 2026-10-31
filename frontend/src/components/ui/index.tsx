// Small shadcn/ui-style primitives (cva + tailwind-merge). They can be swapped for the
// generated shadcn/ui components later without changing call sites.
import { cva, type VariantProps } from "class-variance-authority";
import { clsx, type ClassValue } from "clsx";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { twMerge } from "tailwind-merge";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-brand text-brand-ink hover:bg-brand/90",
        outline: "border border-line bg-surface hover:bg-bg",
        ghost: "hover:bg-brand-soft text-ink",
        danger: "bg-bad text-white hover:bg-bad/90",
        subtle: "bg-brand-soft text-brand hover:bg-brand-soft/70",
      },
      size: { sm: "h-8 px-3", md: "h-10 px-4", lg: "h-12 px-6 text-base" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export function Button({
  className, variant, size, loading, children, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & { loading?: boolean }) {
  return (
    <button className={cn(buttonVariants({ variant, size }), className)} disabled={loading || props.disabled} {...props}>
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-line bg-surface p-5 shadow-sm", className)} {...p} />;
}
export function CardTitle({ className, ...p }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("mb-3 text-base font-semibold", className)} {...p} />;
}

const badgeVariants = cva("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    tone: {
      neutral: "bg-bg text-muted border border-line",
      brand: "bg-brand-soft text-brand",
      good: "bg-good-soft text-good",
      warn: "bg-warn-soft text-warn",
      bad: "bg-bad-soft text-bad",
    },
  },
  defaultVariants: { tone: "neutral" },
});
export function Badge({ className, tone, ...p }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...p} />;
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn("h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm", className)} {...p} />
));
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn("w-full rounded-lg border border-line bg-surface p-3 text-sm", className)} {...p} />
));
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(({ className, ...p }, ref) => (
  <select ref={ref} className={cn("h-10 w-full rounded-lg border border-line bg-surface px-2 text-sm", className)} {...p} />
));

export function Field({ label, error, hint, children, htmlFor }: { label: string; error?: string; hint?: string; children: React.ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium">{label}</label>
      {children}
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && <p className="text-xs text-bad" role="alert">{error}</p>}
    </div>
  );
}

export function Progress({ value, className, label }: { value: number; className?: string; label?: string }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-line", className)} role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${v}%` }} />
    </div>
  );
}

export function Alert({ tone = "brand", title, children }: { tone?: "brand" | "warn" | "bad" | "good"; title?: string; children?: React.ReactNode }) {
  const tones = { brand: "bg-brand-soft border-brand/30", warn: "bg-warn-soft border-warn/30", bad: "bg-bad-soft border-bad/30", good: "bg-good-soft border-good/30" };
  return (
    <div className={cn("rounded-lg border p-3 text-sm", tones[tone])} role={tone === "bad" ? "alert" : "status"}>
      {title && <p className="font-semibold">{title}</p>}
      {children}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line p-8 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}…
    </div>
  );
}

export function Score({ value, label, sub }: { value: number | null | undefined; label: string; sub?: string }) {
  return (
    <div>
      <p className="text-xs text-muted">{label}</p>
      <p className="text-3xl font-semibold tabular-nums">{value == null ? "–" : Math.round(value)}<span className="text-base text-muted">{value == null ? "" : "/100"}</span></p>
      {sub && <p className="text-xs text-muted">{sub}</p>}
    </div>
  );
}

export function PageHeader({ title, children, actions }: { title: string; children?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {children && <div className="mt-1 text-sm text-muted">{children}</div>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export const statusTone = (s: string): "good" | "warn" | "bad" | "neutral" | "brand" =>
  ({ demonstrated: "good", met: "good", verified: "good", completed: "good", final: "brand", listed: "warn", transferable: "warn",
     provisional: "warn", partly_assessed: "brand", stale: "warn", unverified: "neutral", missing: "bad", broken: "bad", insufficient: "warn",
     high: "good", medium: "brand", low: "warn" } as Record<string, "good" | "warn" | "bad" | "neutral" | "brand">)[s] ?? "neutral";
