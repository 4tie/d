import React from "react";
import { cx } from "./primitives";

// Spinner Component
export function Spinner({ className, size = "md" }: { className?: string; size?: "sm" | "md" | "lg" }) {
    const sizeClass = size === "sm" ? "h-4 w-4" : size === "lg" ? "h-8 w-8" : "h-6 w-6";

    return (
        <svg
            className={cx("animate-spin", sizeClass, className)}
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
        >
            <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
            />
            <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
        </svg>
    );
}

// Skeleton Loaders
export function SkeletonText({ className, lines = 1 }: { className?: string; lines?: number }) {
    return (
        <div className={cx("space-y-2", className)}>
            {Array.from({ length: lines }).map((_, i) => (
                <div
                    key={i}
                    className="h-4 bg-panel-750 rounded animate-shimmer"
                    style={{ width: i === lines - 1 ? "80%" : "100%" }}
                />
            ))}
        </div>
    );
}

export function SkeletonCard({ className }: { className?: string }) {
    return (
        <div className={cx("rounded-xl border border-border-700 bg-panel-800 p-3", className)}>
            <div className="h-5 w-32 bg-panel-750 rounded animate-shimmer mb-3" />
            <SkeletonText lines={3} />
        </div>
    );
}

export function SkeletonMetric({ className }: { className?: string }) {
    return (
        <div className={cx("rounded-xl border border-border-700 bg-panel-800 px-3 py-2", className)}>
            <div className="h-3 w-24 bg-panel-750 rounded animate-shimmer mb-2" />
            <div className="h-8 w-20 bg-panel-750 rounded animate-shimmer" />
        </div>
    );
}

export function SkeletonChart({ className }: { className?: string }) {
    return (
        <div className={cx("rounded-xl border border-border-700 bg-panel-800 p-3", className)}>
            <div className="h-5 w-40 bg-panel-750 rounded animate-shimmer mb-3" />
            <div className="h-64 bg-panel-750 rounded animate-shimmer" />
        </div>
    );
}

// Full Page Loading
export function PageLoading({ message = "Loading..." }: { message?: string }) {
    return (
        <div className="flex flex-col items-center justify-center min-h-[400px] animate-fade-in">
            <Spinner size="lg" className="text-semantic-info mb-4" />
            <div className="text-sm text-fg-400">{message}</div>
        </div>
    );
}

// Inline Loading with message
export function InlineLoading({ message }: { message?: string }) {
    return (
        <div className="flex items-center gap-2 text-sm text-fg-400 animate-fade-in">
            <Spinner size="sm" className="text-semantic-info" />
            {message && <span>{message}</span>}
        </div>
    );
}

// Empty State Component
export function EmptyState({
    icon,
    title,
    description,
    action,
}: {
    icon?: React.ReactNode;
    title: string;
    description?: string;
    action?: React.ReactNode;
}) {
    return (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center animate-fade-in">
            {icon && <div className="mb-4 text-fg-400 opacity-50">{icon}</div>}
            <h3 className="text-lg font-medium text-fg-200 mb-2">{title}</h3>
            {description && <p className="text-sm text-fg-400 mb-4 max-w-sm">{description}</p>}
            {action && <div className="mt-2">{action}</div>}
        </div>
    );
}
