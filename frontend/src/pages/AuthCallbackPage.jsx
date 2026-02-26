import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

export default function AuthCallbackPage() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { login } = useAuth();

    useEffect(() => {
        const handleAuth = async () => {
            const token = searchParams.get('token');
            const error = searchParams.get('error');

            if (error) {
                console.error('Auth error:', error);
                navigate('/?error=' + encodeURIComponent(error));
                return;
            }

            if (token) {
                await login(token);
                navigate('/app');
            } else {
                navigate('/');
            }
        };

        handleAuth();
    }, [searchParams, login, navigate]);

    return (
        <div className="min-h-screen bg-background flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
                <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-muted-foreground font-mono text-sm">AUTHENTICATING...</span>
            </div>
        </div>
    );
}
