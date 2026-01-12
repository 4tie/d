import React, { useState, useEffect, useRef } from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Card(props: {
  title?: string;
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glass?: boolean;
}) {
  return (
    <div className={cx(
      "rounded-xl border border-border-700 bg-panel-800 animate-fade-in",
      props.hover && "card-hover cursor-pointer",
      props.glass && "glass-effect",
      props.className
    )}>
      {props.title ? <div className="px-3 pt-3 text-sm text-fg-200 font-medium">{props.title}</div> : null}
      <div className={cx("px-3", props.title ? "pb-3 pt-2" : "py-3")}>{props.children}</div>
    </div>
  );
}

export function Button(props: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "primary" | "secondary" | "outline" | "danger";
  className?: string;
  type?: "button" | "submit";
}) {
  const v = props.variant || "secondary";
  const base = "inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200";

  const cls =
    v === "primary"
      ? "bg-semantic-info text-white hover:opacity-90 hover:shadow-lg"
      : v === "danger"
        ? "bg-semantic-neg text-white hover:opacity-90 hover:shadow-lg"
        : v === "outline"
          ? "border border-border-700 text-fg-200 hover:bg-panel-750 hover:border-border-650"
          : "bg-panel-750 text-fg-200 hover:bg-panel-900";

  const isDisabled = props.disabled || props.loading;

  return (
    <button
      type={props.type || "button"}
      disabled={isDisabled}
      onClick={props.onClick}
      className={cx(
        base,
        cls,
        isDisabled ? "opacity-50 cursor-not-allowed" : "active:scale-95",
        props.className
      )}
    >
      {props.loading && (
        <svg
          className="animate-spin h-4 w-4"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      )}
      {props.children}
    </button>
  );
}

export function Input(props: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  type?: string;
  list?: string;
  disabled?: boolean;
  clearable?: boolean;
}) {
  const showClear = props.clearable && props.value && !props.disabled;

  return (
    <div className="relative">
      <input
        type={props.type || "text"}
        value={props.value}
        list={props.list}
        disabled={props.disabled}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
        className={cx(
          "w-full rounded-md border border-border-700 bg-bg-900 px-3 py-2 text-sm text-fg-100 placeholder:text-fg-400",
          "focus:outline-none focus:ring-2 focus:ring-semantic-info/30 focus:border-semantic-info/50",
          "transition-all duration-200",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          showClear && "pr-10",
          props.className
        )}
      />
      {showClear && (
        <button
          type="button"
          onClick={() => props.onChange("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-panel-750 text-fg-400 hover:text-fg-200 transition-colors"
          aria-label="Clear"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}

export function TokenInput(props: {
  tokens: string[];
  onTokensChange: (v: string[]) => void;
  draft: string;
  onDraftChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  suggestions?: string[];
  listId?: string;
}) {
  const listId = props.listId || React.useId();

  function splitTokens(s: string): string[] {
    return String(s || "")
      .split(/[,;\n]+/g)
      .map((x) => x.trim())
      .filter(Boolean);
  }

  function addTokens(nextTokens: string[]) {
    const next = Array.isArray(props.tokens) ? [...props.tokens] : [];
    for (const t of nextTokens) {
      if (t && !next.includes(t)) next.push(t);
    }
    props.onTokensChange(next);
  }

  function commitDraft() {
    const parts = splitTokens(props.draft);
    if (parts.length) addTokens(parts);
    props.onDraftChange("");
  }

  function removeAt(idx: number) {
    const next = (props.tokens || []).filter((_, i) => i !== idx);
    props.onTokensChange(next);
  }

  const disabled = !!props.disabled;
  const hasSuggestions = Array.isArray(props.suggestions) && props.suggestions.length > 0;

  return (
    <div
      className={cx(
        "w-full rounded-md border border-border-700 bg-bg-900 px-2 py-2",
        "focus-within:ring-2 focus-within:ring-semantic-info/30 focus-within:border-semantic-info/50",
        "transition-all duration-200",
        disabled ? "opacity-50 cursor-not-allowed" : "",
        props.className
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {(props.tokens || []).map((t, idx) => (
          <span
            key={`${t}-${idx}`}
            className="inline-flex items-center gap-2 rounded-md border border-border-700 bg-panel-750 px-2 py-1 text-xs font-mono text-fg-100 animate-slide-up"
          >
            <span>{t}</span>
            <button
              type="button"
              disabled={disabled}
              onClick={() => removeAt(idx)}
              className={cx(
                "rounded px-1 text-fg-300 hover:bg-panel-800 hover:text-semantic-neg transition-colors",
                disabled ? "cursor-not-allowed" : ""
              )}
            >
              ×
            </button>
          </span>
        ))}

        <input
          value={props.draft}
          disabled={disabled}
          list={hasSuggestions ? listId : undefined}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => props.onDraftChange(e.target.value)}
          onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              commitDraft();
              return;
            }
            if (e.key === "Backspace" && !props.draft && (props.tokens || []).length > 0) {
              e.preventDefault();
              removeAt((props.tokens || []).length - 1);
              return;
            }
          }}
          onBlur={() => {
            if (props.draft.trim()) commitDraft();
          }}
          onPaste={(e: React.ClipboardEvent<HTMLInputElement>) => {
            const text = e.clipboardData.getData("text");
            if (typeof text === "string" && /[,;\n]/.test(text)) {
              e.preventDefault();
              addTokens(splitTokens(text));
            }
          }}
          placeholder={props.placeholder}
          className={cx(
            "min-w-[160px] flex-1 bg-transparent px-1 py-1 text-sm text-fg-100 placeholder:text-fg-400",
            "focus:outline-none"
          )}
        />
      </div>

      {hasSuggestions ? (
        <datalist id={listId}>
          {(props.suggestions || []).map((s: string) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      ) : null}
    </div>
  );
}

export function Textarea(props: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  rows?: number;
  disabled?: boolean;
}) {
  return (
    <textarea
      value={props.value}
      disabled={props.disabled}
      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => props.onChange(e.target.value)}
      placeholder={props.placeholder}
      rows={props.rows || 6}
      className={cx(
        "w-full rounded-md border border-border-700 bg-bg-900 px-3 py-2 text-sm text-fg-100 placeholder:text-fg-400",
        "font-mono focus:outline-none focus:ring-2 focus:ring-semantic-info/30 focus:border-semantic-info/50",
        "transition-all duration-200",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        props.className
      )}
    />
  );
}

// Animated Number Component
function AnimatedNumber({ value }: { value: number }) {
  const [displayValue, setDisplayValue] = useState(value);
  const animationRef = useRef<number>();

  useEffect(() => {
    const start = displayValue;
    const end = value;
    const duration = 800;
    const startTime = performance.now();

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = start + (end - start) * eased;

      setDisplayValue(current);

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      }
    };

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [value]);

  return <>{displayValue.toFixed(2)}</>;
}

export function Metric(props: {
  label: string;
  value: string;
  tone?: "pos" | "neg" | "warn" | "neutral";
  animated?: boolean;
  trend?: "up" | "down" | null;
}) {
  const tone = props.tone || "neutral";
  const vClass =
    tone === "pos"
      ? "text-semantic-pos"
      : tone === "neg"
        ? "text-semantic-neg"
        : tone === "warn"
          ? "text-semantic-warn"
          : "text-fg-100";

  const trendIcon = props.trend === "up" ? (
    <svg className="w-5 h-5 text-semantic-pos" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
    </svg>
  ) : props.trend === "down" ? (
    <svg className="w-5 h-5 text-semantic-neg" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
    </svg>
  ) : null;

  return (
    <div className="rounded-xl border border-border-700 bg-panel-800 px-3 py-2 animate-slide-up hover:border-border-650 transition-colors">
      <div className="flex items-center justify-between">
        <div className="text-xs text-fg-400 uppercase tracking-wide">{props.label}</div>
        {trendIcon}
      </div>
      <div className={cx("mt-1 text-2xl font-bold font-mono", vClass)}>
        {props.value}
      </div>
    </div>
  );
}
