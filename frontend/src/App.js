import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { getSettings } from "@/lib/api";

// Pages
import SetupPage from "@/pages/SetupPage";
import DashboardPage from "@/pages/DashboardPage";
import PromptEditorPage from "@/pages/PromptEditorPage";
import TemplatesPage from "@/pages/TemplatesPage";
import ApiKeysPage from "@/pages/ApiKeysPage";
import SettingsPage from "@/pages/SettingsPage";

// Layout
import MainLayout from "@/components/layout/MainLayout";

function App() {
  const [isConfigured, setIsConfigured] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkConfiguration();
  }, []);

  const checkConfiguration = async () => {
    try {
      const response = await getSettings();
      setIsConfigured(response.data.is_configured);
    } catch (error) {
      console.error("Error checking configuration:", error);
      setIsConfigured(false);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-muted-foreground font-mono text-sm">INITIALIZING...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route 
            path="/setup" 
            element={
              <SetupPage onConfigured={() => setIsConfigured(true)} />
            } 
          />
          <Route 
            path="/*" 
            element={
              isConfigured ? (
                <MainLayout>
                  <Routes>
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/prompts/:promptId" element={<PromptEditorPage />} />
                    <Route path="/templates" element={<TemplatesPage />} />
                    <Route path="/api-keys" element={<ApiKeysPage />} />
                    <Route path="/settings" element={<SettingsPage onDisconnect={() => setIsConfigured(false)} />} />
                  </Routes>
                </MainLayout>
              ) : (
                <Navigate to="/setup" replace />
              )
            } 
          />
        </Routes>
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
