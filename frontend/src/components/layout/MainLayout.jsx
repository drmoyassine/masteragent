import { NavLink } from "react-router-dom";
import { 
  LayoutDashboard, 
  FileText, 
  Key, 
  Settings,
  Sparkles
} from "lucide-react";

export const MainLayout = ({ children }) => {
  const navItems = [
    { path: "/", icon: LayoutDashboard, label: "Prompts" },
    { path: "/templates", icon: Sparkles, label: "Templates" },
    { path: "/api-keys", icon: Key, label: "API Keys" },
    { path: "/settings", icon: Settings, label: "Settings" },
  ];

  return (
    <div className="app-container" data-testid="main-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-sm bg-primary flex items-center justify-center">
              <FileText className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="font-mono font-semibold text-foreground tracking-tight">
              PROMPTSRC
            </span>
          </div>
        </div>
        
        <nav className="sidebar-nav">
          <div className="space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) => 
                  `nav-item ${isActive ? 'active' : ''}`
                }
                data-testid={`nav-${item.label.toLowerCase().replace(' ', '-')}`}
              >
                <item.icon className="w-4 h-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>
        
        <div className="p-4 border-t border-border">
          <div className="text-xs text-muted-foreground font-mono">
            <span className="text-primary">v1.0.0</span> • Prompt Manager
          </div>
        </div>
      </aside>
      
      {/* Main Content */}
      <main className="main-content">
        {children}
      </main>
    </div>
  );
};

export default MainLayout;
