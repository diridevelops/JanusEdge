import {
    createContext,
    useCallback,
    useMemo,
    useState,
    type ReactNode,
} from 'react';

type ToastType = 'success' | 'error' | 'info' | 'warning';

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastState {
  toasts: Toast[];
  addToast: (type: ToastType, message: string) => void;
  removeToast: (id: number) => void;
}

export const ToastContext = createContext<ToastState>({
  toasts: [],
  addToast: () => {},
  removeToast: () => {},
});

interface ToastProviderProps {
  children: ReactNode;
}

let nextId = 0;

/** Provides toast notification state and methods. */
export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (type: ToastType, message: string) => {
      const id = ++nextId;
      setToasts((prev) => [...prev, { id, type, message }]);
      // Auto-remove after 5 seconds
      setTimeout(() => removeToast(id), 5000);
    },
    [removeToast]
  );

  const value = useMemo(
    () => ({ toasts, addToast, removeToast }),
    [toasts, addToast, removeToast]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
    </ToastContext.Provider>
  );
}
