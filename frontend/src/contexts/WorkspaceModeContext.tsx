import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getWorkspaceMode, updateWorkspaceMode } from '../api/workspace.api';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import type { WorkspaceMode } from '../types/workspace.types';

interface WorkspaceModeState {
  activeMode: WorkspaceMode;
  isLoading: boolean;
  loadError: boolean;
  isSaving: boolean;
  reloadWorkspaceMode: () => void;
  setActiveMode: (mode: WorkspaceMode) => Promise<void>;
}

export const WorkspaceModeContext = createContext<WorkspaceModeState>({
  activeMode: 'real',
  isLoading: true,
  loadError: false,
  isSaving: false,
  reloadWorkspaceMode: () => {},
  setActiveMode: async () => {},
});

interface WorkspaceModeProviderProps {
  children: ReactNode;
}

function isWorkspaceMode(value: unknown): value is WorkspaceMode {
  return value === 'real' || value === 'backtest';
}

/** Loads and persists the authenticated user's active workspace. */
export function WorkspaceModeProvider({ children }: WorkspaceModeProviderProps) {
  const { user, isLoading: isAuthLoading } = useAuth();
  const { addToast } = useToast();
  const [activeMode, setActiveModeState] = useState<WorkspaceMode>('real');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  const reloadWorkspaceMode = useCallback(() => {
    setLoadAttempt((attempt) => attempt + 1);
  }, []);

  useEffect(() => {
    let isCurrent = true;

    if (isAuthLoading) {
      setIsLoading(true);
      setLoadError(false);
      return () => {
        isCurrent = false;
      };
    }

    if (!user?.id) {
      setActiveModeState('real');
      setIsLoading(false);
      setLoadError(false);
      return () => {
        isCurrent = false;
      };
    }

    setIsLoading(true);
    setLoadError(false);
    getWorkspaceMode()
      .then(({ active_mode }) => {
        if (!isCurrent) return;
        if (!isWorkspaceMode(active_mode)) {
          throw new Error('The server returned an unsupported workspace mode.');
        }
        setActiveModeState(active_mode);
      })
      .catch(() => {
        if (!isCurrent) return;
        setLoadError(true);
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [user?.id, isAuthLoading, loadAttempt]);

  const setActiveMode = useCallback(
    async (mode: WorkspaceMode) => {
      if (mode === activeMode || isSaving) return;

      setIsSaving(true);
      try {
        const response = await updateWorkspaceMode({ active_mode: mode });
        if (!isWorkspaceMode(response.active_mode)) {
          throw new Error('The server returned an unsupported workspace mode.');
        }
        setActiveModeState(response.active_mode);
      } catch (error) {
        addToast('error', 'Could not save your workspace selection.');
        throw error;
      } finally {
        setIsSaving(false);
      }
    },
    [activeMode, isSaving, addToast]
  );

  const value = useMemo(
    () => ({
      activeMode,
      isLoading,
      loadError,
      isSaving,
      reloadWorkspaceMode,
      setActiveMode,
    }),
    [activeMode, isLoading, loadError, isSaving, reloadWorkspaceMode, setActiveMode]
  );

  return (
    <WorkspaceModeContext.Provider value={value}>
      {children}
    </WorkspaceModeContext.Provider>
  );
}

/** Read workspace state and the persisted mode-switch action. */
export function useWorkspaceMode() {
  return useContext(WorkspaceModeContext);
}
