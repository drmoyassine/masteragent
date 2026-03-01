import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getAuthStatus } from '@/lib/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    const checkAuth = useCallback(async () => {
        const token = localStorage.getItem('auth_token');
        if (!token) {
            setUser(null);
            setIsAuthenticated(false);
            setLoading(false);
            return;
        }

        try {
            const response = await getAuthStatus();
            if (response.data.authenticated) {
                setUser(response.data.user);
                setIsAuthenticated(true);
            } else {
                console.warn('Authentication token invalid, clearing session');
                localStorage.removeItem('auth_token');
                setUser(null);
                setIsAuthenticated(false);
            }
        } catch (error) {
            console.error('Auth verification failed:', error);
            // Only clear on definitive 401/403 (handled by interceptor but good to be explicit)
            if (error.response?.status === 401 || error.response?.status === 403) {
                localStorage.removeItem('auth_token');
                setUser(null);
                setIsAuthenticated(false);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        checkAuth();
    }, [checkAuth]);

    const login = async (token) => {
        localStorage.setItem('auth_token', token);
        await checkAuth();
    };

    const logout = () => {
        localStorage.removeItem('auth_token');
        setUser(null);
        setIsAuthenticated(false);
    };

    return (
        <AuthContext.Provider value={{ user, isAuthenticated, loading, login, logout, checkAuth }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
