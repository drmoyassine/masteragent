import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ConfigProvider, useConfig } from "@/context/ConfigContext";

// Pages
import LandingPage from "@/pages/LandingPage";
import AuthPage from "@/pages/AuthPage";
import AuthCallbackPage from "@/pages/AuthCallbackPage";
import SetupPage from "@/pages/SetupPage";
import DashboardPage from "@/pages/DashboardPage";
import PromptEditorPage from "@/pages/PromptEditorPage";
import TemplatesPage from "@/pages/TemplatesPage";
import ApiKeysPage from "@/pages/ApiKeysPage";
import SettingsPage from "@/pages/SettingsPage";
import MemorySettingsPage from "@/pages/MemorySettingsPage";
import MemoryExplorerPage from "@/pages/MemoryExplorerPage";
import MemoryMonitorPage from "@/pages/MemoryMonitorPage";

// Layout
import MainLayout from "@/components/layout/MainLayout";

// Protected Route Component
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  const { loading: configLoading } = useConfig();
  const location = useLocation();

  if (loading || configLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-muted-foreground font-mono text-sm">LOADING...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  return children;
};

// App Content - All routes accessible, warnings shown via MainLayout
const AppContent = () => {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/auth" element={<AuthPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />

      {/* Protected Routes */}
      <Route
        path="/app/*"
        element={
          <ProtectedRoute>
            <MainLayout>
              <Routes>
                <Route index element={<DashboardPage />} />
                <Route path="prompts/:promptId" element={<PromptEditorPage />} />
                <Route path="templates" element={<TemplatesPage />} />
                <Route path="api-keys" element={<ApiKeysPage />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="memory" element={<MemorySettingsPage />} />
                <Route path="memory/explore" element={<MemoryExplorerPage />} />
                <Route path="memory/monitor" element={<MemoryMonitorPage />} />
                <Route path="setup" element={<SetupPage />} />
              </Routes>
            </MainLayout>
          </ProtectedRoute>
        }
      />

      {/* Catch all - redirect to home */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <ConfigProvider>
            <AppContent />
          </ConfigProvider>
        </AuthProvider>
      </BrowserRouter>
      <Toaster 
        position="bottom-right"
        toastOptions={{
          style: {
            background: 'hsl(240 10% 3.9%)',
            border: '1px solid hsl(240 4% 16%)',
            color: 'hsl(0 0% 98%)',
          },
        }}
      />
    </div>
  );
}

export default App;
