import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

type ToastTone = "success" | "error" | "info";

interface ToastInput {
  tone?: ToastTone;
  title: string;
  description?: string;
}

interface ToastItem extends ToastInput { id: number; tone: ToastTone }

interface ToastApi {
  notify: (toast: ToastInput) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
}

const NOOP: ToastApi = { notify: () => {}, success: () => {}, error: () => {} };
const ToastContext = createContext<ToastApi>(NOOP);

/** Success toasts clear themselves; errors stay until dismissed so they are never missed. */
const SUCCESS_MS = 4500;
const MAX_VISIBLE = 3;

const ICON: Record<ToastTone, ReactNode> = {
  success: <CheckCircle2 size={16} aria-hidden="true" />,
  error: <AlertCircle size={16} aria-hidden="true" />,
  info: <Info size={16} aria-hidden="true" />,
};

/** Outside a provider the hook is a no-op, so components stay renderable in isolation. */
export function useToast(): ToastApi {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setItems(list => list.filter(t => t.id !== id));
  }, []);

  const notify = useCallback((toast: ToastInput) => {
    const id = nextId.current++;
    const tone = toast.tone ?? "info";
    setItems(list => [...list, { ...toast, id, tone }].slice(-MAX_VISIBLE));
    if (tone !== "error") timers.current.set(id, window.setTimeout(() => dismiss(id), SUCCESS_MS));
  }, [dismiss]);

  useEffect(() => {
    const active = timers.current;
    return () => active.forEach(t => window.clearTimeout(t));
  }, []);

  const api = useMemo<ToastApi>(() => ({
    notify,
    success: (title, description) => notify({ tone: "success", title, description }),
    error: (title, description) => notify({ tone: "error", title, description }),
  }), [notify]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" aria-label="Notifications">
        {items.map(t => (
          <div
            key={t.id}
            className={`toast toast-${t.tone}`}
            role={t.tone === "error" ? "alert" : "status"}
          >
            <span className="toast-icon">{ICON[t.tone]}</span>
            <div className="toast-body">
              <strong>{t.title}</strong>
              {t.description && <p>{t.description}</p>}
            </div>
            <button type="button" className="toast-close" aria-label={`Dismiss: ${t.title}`} onClick={() => dismiss(t.id)}>
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
