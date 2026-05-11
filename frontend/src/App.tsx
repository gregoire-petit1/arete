import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navigation } from '@/components';
import { SettingsProvider } from '@/contexts';
import {
  HUDPage,
  QuestLogPage,
  MatrixPage,
  ForgePage,
  NeuralLinkPage,
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
                <Route path="/" element={<HUDPage />} />
                <Route path="/quest-log" element={<QuestLogPage />} />
                <Route path="/forge" element={<ForgePage />} />
                <Route path="/neural-link" element={<NeuralLinkPage />} />
                <Route path="/matrix" element={<MatrixPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </main>
          </div>
        </BrowserRouter>
      </SettingsProvider>
    </QueryClientProvider>
  );
}

export default App;
