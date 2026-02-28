import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getSettings } from '@/lib/api';
import { useAuth } from './AuthContext';

const ConfigContext = createContext(null);

export const ConfigProvider = ({ children }) => {
    const { isAuthenticated } = useAuth();
    const [isConfigured, setIsConfigured] = useState(null);
    const [storageMode, setStorageMode] = useState(null); // 'github', 'local', or null
    const [hasGitHub, setHasGitHub] = useState(false);
    const [loading, setLoading] = useState(true);

    const checkConfiguration = useCallback(async () => {
        if (!isAuthenticated) {
            setLoading(false);
            return;
        }

        try {
            const response = await getSettings();
            setIsConfigured(response.data.is_configured);
            setHasGitHub(response.data.has_github);
            setStorageMode(response.data.storage_mode || (response.data.is_configured ? 'github' : 'local'));
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
        hasGitHub,
        loading,
        checkConfiguration,
        markConfigured,
        markDisconnected,
        // Helper to check if GitHub features are fully configured
        hasGitHubAccess: isConfigured && storageMode === 'github' && hasGitHub,
        // Helper to check if any storage is configured
        hasStorage: isConfigured || hasGitHub,
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
