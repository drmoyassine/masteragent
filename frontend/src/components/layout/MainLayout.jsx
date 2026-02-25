import { NavLink } from "react-router-dom";
import { 
  LayoutDashboard, 
  FileText, 
  Key, 
  Settings,
  Sparkles,
  LogOut,
  Brain
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";

export const MainLayout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const navItems = [
    { path: "/app", icon: LayoutDashboard, label: "Prompts" },
    { path: "/app/templates", icon: Sparkles, label: "Templates" },
    { path: "/app/api-keys", icon: Key, label: "API Keys" },
    { path: "/app/memory", icon: Brain, label: "Memory System" },
    { path: "/app/settings", icon: Settings, label: "Settings" },
  ];

  const handleLogout = () => {
    logout();
    navigate('/');
  };

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
                end={item.path === "/app"}
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
        
        {/* User Section */}
        <div className="p-4 border-t border-border">
          {user && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="w-full justify-start gap-3 px-2 h-auto py-2">
                  <Avatar className="w-8 h-8">
                    <AvatarImage src={user.avatar_url} alt={user.username} />
                    <AvatarFallback className="bg-primary/10 text-primary text-xs font-mono">
                      {user.username?.slice(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 text-left">
                    <div className="text-sm font-mono truncate">{user.username}</div>
                    <Badge variant="outline" className="text-[10px] font-mono uppercase mt-0.5">
                      {user.plan || 'free'}
                    </Badge>
                  </div>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem disabled className="text-xs text-muted-foreground">
                  {user.email}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} className="text-destructive">
                  <LogOut className="w-4 h-4 mr-2" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <div className="text-xs text-muted-foreground font-mono mt-3">
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
