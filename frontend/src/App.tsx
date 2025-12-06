import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navigation } from '@/components';
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
      <BrowserRouter>
        <div className="min-h-screen bg-void">
          <Navigation />
          <main>
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
    </QueryClientProvider>
  );
}

export default App;
