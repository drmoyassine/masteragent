import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { getSettings } from "@/lib/api";

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

// Layout
import MainLayout from "@/components/layout/MainLayout";

// Protected Route Component
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
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

// App Content with GitHub Setup Check
const AppContent = () => {
  const { isAuthenticated } = useAuth();
  const [isConfigured, setIsConfigured] = useState(null);
  const [checkingConfig, setCheckingConfig] = useState(true);

  useEffect(() => {
    if (isAuthenticated) {
      checkConfiguration();
    } else {
      setCheckingConfig(false);
    }
  }, [isAuthenticated]);

  const checkConfiguration = async () => {
    try {
      const response = await getSettings();
      setIsConfigured(response.data.is_configured);
    } catch (error) {
      console.error("Error checking configuration:", error);
      setIsConfigured(false);
    } finally {
      setCheckingConfig(false);
    }
  };

  if (checkingConfig && isAuthenticated) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-muted-foreground font-mono text-sm">CHECKING CONFIGURATION...</span>
        </div>
      </div>
    );
  }

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
            {isConfigured === false ? (
              <SetupPage onConfigured={() => setIsConfigured(true)} />
            ) : (
              <MainLayout>
                <Routes>
                  <Route index element={<DashboardPage />} />
                  <Route path="prompts/:promptId" element={<PromptEditorPage />} />
                  <Route path="templates" element={<TemplatesPage />} />
                  <Route path="api-keys" element={<ApiKeysPage />} />
                  <Route path="settings" element={<SettingsPage onDisconnect={() => setIsConfigured(false)} />} />
                  <Route path="setup" element={<SetupPage onConfigured={() => setIsConfigured(true)} />} />
                </Routes>
              </MainLayout>
            )}
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
          <AppContent />
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
