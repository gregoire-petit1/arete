import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navigation } from '@/components';
import { SettingsProvider } from '@/contexts';
import {
  DashboardPage,
  PlanningPage,
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
  return (
    <QueryClientProvider client={queryClient}>
      <SettingsProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-void">
            <Navigation />
            {/* pb-20 on mobile for bottom tab bar clearance, pb-0 on desktop */}
            <main className="pb-20 md:pb-0">
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/planning" element={<PlanningPage />} />
                <Route path="/log" element={<LogPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                {/* Legacy redirects */}
                <Route path="/quest-log" element={<Navigate to="/planning" replace />} />
                <Route path="/forge" element={<Navigate to="/log" replace />} />
                <Route path="/matrix" element={<Navigate to="/settings" replace />} />
                <Route path="/neural-link" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </BrowserRouter>
      </SettingsProvider>
    </QueryClientProvider>
  );
}

export default App;
