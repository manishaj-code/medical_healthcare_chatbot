import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import ToastCard from "./ToastCard";

export interface ToastItem {
  id: string;
  title: string;
  message: string;
  icon?: string;
  variant?: "info" | "success" | "error" | "urgent";
  chipLabel?: string;
  durationMs?: number;
}

interface ToastContextValue {
  showToast: (toast: Omit<ToastItem, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);
const DEDUPE_MS = 15_000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const recentKeysRef = useRef<Map<string, number>>(new Map());

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback((toast: Omit<ToastItem, "id">) => {
    const now = Date.now();
    const titleKey = `${toast.variant ?? "info"}|${toast.title}`;
    const fullKey = `${titleKey}|${toast.message}`;
    for (const [key, at] of recentKeysRef.current) {
      if (now - at > DEDUPE_MS) recentKeysRef.current.delete(key);
    }
    if (recentKeysRef.current.has(titleKey) || recentKeysRef.current.has(fullKey)) return;
    recentKeysRef.current.set(titleKey, now);
    recentKeysRef.current.set(fullKey, now);

    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const item: ToastItem = { id, ...toast };
    setToasts((prev) => [...prev, item].slice(-3));
  }, []);

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-relevant="additions">
        {toasts.map((toast, index) => (
          <div
            key={toast.id}
            className="toast-stack-item"
            style={{ "--toast-index": index } as React.CSSProperties}
          >
            <ToastCard toast={toast} onDismiss={dismissToast} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}
