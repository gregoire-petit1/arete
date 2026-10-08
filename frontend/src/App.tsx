import { useCallback, useRef, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navigation, ErrorBoundary } from '@/components';
import { AgentSidePanel } from '@/components/AgentSidePanel';
import { SettingsProvider } from '@/contexts';
import {
  DashboardPage,
  PlanningPage,
  AnalyticsPage,
  LogPage,
  SettingsPage,
} from '@/pages';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: 1,
    },
  },
});

function App() {
  // Panel state lives above the router so the drawer survives page navigation
  // (the agent's panel_context follows the route, the conversation too).
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const closeAgent = useCallback(() => {
    setAgentOpen(false);
    triggerRef.current?.focus();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <SettingsProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-void">
            <Navigation
              agentOpen={agentOpen}
              agentBusy={agentBusy}
              onToggleAgent={(event) => {
                triggerRef.current = event.currentTarget;
                setAgentOpen((v) => !v);
              }}
            />
            {/* pb-20 on mobile for bottom tab bar clearance, pb-0 on desktop */}
            <main
              className={`pb-20 md:pb-0 transition-[margin] duration-200 motion-reduce:transition-none ${agentOpen ? 'xl:mr-[520px]' : ''}`}
            >
              <ErrorBoundary>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/planning" element={<PlanningPage />} />
                  <Route path="/analytics" element={<AnalyticsPage />} />
                  <Route path="/log" element={<LogPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  {/* Legacy redirects */}
                  <Route
                    path="/quest-log"
                    element={<Navigate to="/planning" replace />}
                  />
                  <Route
                    path="/forge"
                    element={<Navigate to="/log" replace />}
                  />
                  <Route
                    path="/matrix"
                    element={<Navigate to="/settings" replace />}
                  />
                  <Route
                    path="/neural-link"
                    element={<Navigate to="/" replace />}
                  />
                </Routes>
              </ErrorBoundary>
            </main>

            <AgentSidePanel
              open={agentOpen}
              onClose={closeAgent}
              onBusyChange={setAgentBusy}
            />
          </div>
        </BrowserRouter>
      </SettingsProvider>
    </QueryClientProvider>
  );
}

export default App;
