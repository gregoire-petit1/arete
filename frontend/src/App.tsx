import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Bot, X } from 'lucide-react';
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

  return (
    <QueryClientProvider client={queryClient}>
      <SettingsProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-void">
            <Navigation />
            {/* pb-20 on mobile for bottom tab bar clearance, pb-0 on desktop */}
            <main className="pb-20 md:pb-0">
              <ErrorBoundary>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/planning" element={<PlanningPage />} />
                  <Route path="/analytics" element={<AnalyticsPage />} />
                  <Route path="/log" element={<LogPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  {/* Legacy redirects */}
                  <Route path="/quest-log" element={<Navigate to="/planning" replace />} />
                  <Route path="/forge" element={<Navigate to="/log" replace />} />
                  <Route path="/matrix" element={<Navigate to="/settings" replace />} />
                  <Route path="/neural-link" element={<Navigate to="/" replace />} />
                </Routes>
              </ErrorBoundary>
            </main>

            {/* Coach toggle — open AND close on demand (Escape works in-panel too) */}
            <button
              onClick={() => setAgentOpen((v) => !v)}
              className="fixed bottom-24 md:bottom-6 right-4 z-30 p-3 rounded-full bg-neon-purple/20 border border-neon-purple/40 hover:bg-neon-purple/30 shadow-lg"
              aria-label={agentOpen ? 'Fermer le coach IA' : 'Ouvrir le coach IA'}
              aria-expanded={agentOpen}
            >
              {agentOpen ? <X className="size-6 text-neon-cyan" /> : <Bot className="size-6 text-neon-cyan" />}
            </button>
            <AgentSidePanel open={agentOpen} onClose={() => setAgentOpen(false)} />
          </div>
        </BrowserRouter>
      </SettingsProvider>
    </QueryClientProvider>
  );
}

export default App;
