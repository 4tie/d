import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { cx } from "./primitives";

type ToastType = "success" | "error" | "warning" | "info";

interface Toast {
    id: string;
    type: ToastType;
    message: string;
    duration?: number;
}

interface ToastContextValue {
    toasts: Toast[];
    addToast: (type: ToastType, message: string, duration?: number) => void;
    removeToast: (id: string) => void;
    success: (message: string, duration?: number) => void;
    error: (message: string, duration?: number) => void;
    warning: (message: string, duration?: number) => void;
    info: (message: string, duration?: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error("useToast must be used within ToastProvider");
    return ctx;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const addToast = useCallback((type: ToastType, message: string, duration = 5000) => {
        const id = Math.random().toString(36).substring(2, 9);
        const toast: Toast = { id, type, message, duration };

        setToasts((prev) => [...prev, toast]);

        if (duration > 0) {
            setTimeout(() => {
                setToasts((prev) => prev.filter((t) => t.id !== id));
            }, duration);
        }
    }, []);

    const removeToast = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const success = useCallback((message: string, duration?: number) => addToast("success", message, duration), [addToast]);
    const error = useCallback((message: string, duration?: number) => addToast("error", message, duration), [addToast]);
    const warning = useCallback((message: string, duration?: number) => addToast("warning", message, duration), [addToast]);
    const info = useCallback((message: string, duration?: number) => addToast("info", message, duration), [addToast]);

    return (
        <ToastContext.Provider value={{ toasts, addToast, removeToast, success, error, warning, info }}>
            {children}
            <ToastContainer toasts={toasts} removeToast={removeToast} />
        </ToastContext.Provider>
    );
}

function ToastContainer({ toasts, removeToast }: { toasts: Toast[]; removeToast: (id: string) => void }) {
    return (
        <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
            {toasts.map((toast) => (
                <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
            ))}
        </div>
    );
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
    const [progress, setProgress] = useState(100);

    useEffect(() => {
        if (!toast.duration || toast.duration <= 0) return;

        const interval = setInterval(() => {
            setProgress((prev) => {
                const next = prev - (100 / (toast.duration! / 100));
                return next <= 0 ? 0 : next;
            });
        }, 100);

        return () => clearInterval(interval);
    }, [toast.duration]);

    const colors = {
        success: {
            bg: "bg-[#0b2a1a]",
            border: "border-semantic-pos",
            icon: "text-semantic-pos",
            progress: "bg-semantic-pos",
        },
        error: {
            bg: "bg-[#2a0b0b]",
            border: "border-semantic-neg",
            icon: "text-semantic-neg",
            progress: "bg-semantic-neg",
        },
        warning: {
            bg: "bg-[#2a250b]",
            border: "border-semantic-warn",
            icon: "text-semantic-warn",
            progress: "bg-semantic-warn",
        },
        info: {
            bg: "bg-[#0b1f2a]",
            border: "border-semantic-info",
            icon: "text-semantic-info",
            progress: "bg-semantic-info",
        },
    };

    const style = colors[toast.type];

    const icons = {
        success: (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
        ),
        error: (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
        ),
        warning: (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
        ),
        info: (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        ),
    };

    return (
        <div
            className={cx(
                "min-w-[300px] max-w-md rounded-lg border shadow-lg overflow-hidden animate-slide-down pointer-events-auto",
                style.bg,
                style.border
            )}
        >
            <div className="flex items-start gap-3 p-4">
                <div className={style.icon}>{icons[toast.type]}</div>
                <div className="flex-1 min-w-0">
                    <p className="text-sm text-fg-100 break-words">{toast.message}</p>
                </div>
                <button
                    onClick={onClose}
                    className="text-fg-400 hover:text-fg-200 transition-colors shrink-0"
                    aria-label="Close"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            {toast.duration && toast.duration > 0 && (
                <div className="h-1 bg-panel-900">
                    <div
                        className={cx("h-full transition-all duration-100 ease-linear", style.progress)}
                        style={{ width: `${progress}%` }}
                    />
                </div>
            )}
        </div>
    );
}
