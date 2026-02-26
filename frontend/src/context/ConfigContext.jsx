import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getSettings } from '@/lib/api';
import { useAuth } from './AuthContext';

const ConfigContext = createContext(null);

export const ConfigProvider = ({ children }) => {
    const { isAuthenticated } = useAuth();
    const [isConfigured, setIsConfigured] = useState(null);
    const [storageMode, setStorageMode] = useState(null); // 'github', 'local', or null
    const [loading, setLoading] = useState(true);

    const checkConfiguration = useCallback(async () => {
        if (!isAuthenticated) {
            setLoading(false);
            return;
        }

        try {
            const response = await getSettings();
            setIsConfigured(response.data.is_configured);
            setStorageMode(response.data.storage_mode || (response.data.is_configured ? 'github' : null));
        } catch (error) {
            console.error('Error checking configuration:', error);
            setIsConfigured(false);
            setStorageMode(null);
        } finally {
            setLoading(false);
        }
    }, [isAuthenticated]);

    useEffect(() => {
        checkConfiguration();
    }, [checkConfiguration]);

    const markConfigured = (mode = 'github') => {
        setIsConfigured(true);
        setStorageMode(mode);
    };

    const markDisconnected = () => {
        setIsConfigured(false);
        setStorageMode(null);
    };

    const value = {
        isConfigured,
        storageMode,
        loading,
        checkConfiguration,
        markConfigured,
        markDisconnected,
        // Helper to check if GitHub features are available
        hasGitHubAccess: isConfigured && storageMode === 'github',
        // Helper to check if any storage is configured
        hasStorage: isConfigured && (storageMode === 'github' || storageMode === 'local'),
    };

    return (
        <ConfigContext.Provider value={value}>
            {children}
        </ConfigContext.Provider>
    );
};

export const useConfig = () => {
    const context = useContext(ConfigContext);
    if (!context) {
        throw new Error('useConfig must be used within a ConfigProvider');
    }
    return context;
};
