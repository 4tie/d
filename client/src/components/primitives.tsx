import React from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Card(props: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cx("rounded-xl border border-border-700 bg-panel-800", props.className)}>
      {props.title ? <div className="px-3 pt-3 text-sm text-fg-200">{props.title}</div> : null}
      <div className={cx("px-3", props.title ? "pb-3 pt-2" : "py-3")}>{props.children}</div>
    </div>
  );
}

export function Button(props: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "outline" | "danger";
  className?: string;
  type?: "button" | "submit";
}) {
  const v = props.variant || "secondary";
  const base = "inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition";

  const cls =
    v === "primary"
      ? "bg-semantic-info text-white hover:opacity-90"
      : v === "danger"
        ? "bg-semantic-neg text-white hover:opacity-90"
        : v === "outline"
          ? "border border-border-700 text-fg-200 hover:bg-panel-750"
          : "bg-panel-750 text-fg-200 hover:bg-panel-800";

  return (
    <button
      type={props.type || "button"}
      disabled={props.disabled}
      onClick={props.onClick}
      className={cx(base, cls, props.disabled ? "opacity-50 cursor-not-allowed" : "", props.className)}
    >
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
}) {
  return (
    <input
      type={props.type || "text"}
      value={props.value}
      list={props.list}
      onChange={(e: React.ChangeEvent<HTMLInputElement>) => props.onChange(e.target.value)}
      placeholder={props.placeholder}
      className={cx(
        "w-full rounded-md border border-border-700 bg-bg-900 px-3 py-2 text-sm text-fg-100 placeholder:text-fg-400",
        "focus:outline-none focus:ring-2 focus:ring-semantic-info/30",
        props.className
      )}
    />
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
        "focus-within:ring-2 focus-within:ring-semantic-info/30",
        disabled ? "opacity-50 cursor-not-allowed" : "",
        props.className
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {(props.tokens || []).map((t, idx) => (
          <span
            key={`${t}-${idx}`}
            className="inline-flex items-center gap-2 rounded-md border border-border-700 bg-panel-750 px-2 py-1 text-xs font-mono text-fg-100"
          >
            <span>{t}</span>
            <button
              type="button"
              disabled={disabled}
              onClick={() => removeAt(idx)}
              className={cx(
                "rounded px-1 text-fg-300 hover:bg-panel-800",
                disabled ? "cursor-not-allowed" : ""
              )}
            >
              x
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
}) {
  return (
    <textarea
      value={props.value}
      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => props.onChange(e.target.value)}
      placeholder={props.placeholder}
      rows={props.rows || 6}
      className={cx(
        "w-full rounded-md border border-border-700 bg-bg-900 px-3 py-2 text-sm text-fg-100 placeholder:text-fg-400",
        "font-mono focus:outline-none focus:ring-2 focus:ring-semantic-info/30",
        props.className
      )}
    />
  );
}

export function Metric(props: { label: string; value: string; tone?: "pos" | "neg" | "warn" | "neutral" }) {
  const tone = props.tone || "neutral";
  const vClass =
    tone === "pos"
      ? "text-semantic-pos"
      : tone === "neg"
        ? "text-semantic-neg"
        : tone === "warn"
          ? "text-semantic-warn"
          : "text-fg-100";

  return (
    <div className="rounded-xl border border-border-700 bg-panel-800 px-3 py-2">
      <div className="text-xs text-fg-400 uppercase tracking-wide">{props.label}</div>
      <div className={cx("mt-1 text-2xl font-bold font-mono", vClass)}>{props.value}</div>
    </div>
  );
}
