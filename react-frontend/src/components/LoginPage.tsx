import React, { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { apiService, setAuthToken, AuthUser } from '../services/api';
import { getApiErrorMessage } from '../utils/apiErrors';

interface LoginPageProps {
  onLoginSuccess: (user: AuthUser) => void;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onLoginSuccess }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const response = await apiService.login(email, password);
      setAuthToken(response.access_token);
      onLoginSuccess(response.user);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Login failed. Please check your credentials.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f7f7f7] flex flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-[586px] bg-white border border-gray-200 rounded-xl shadow-md px-10 py-10 sm:px-12">
        <div className="text-center mb-10">
          <h1 className="text-[28px] font-extrabold text-red-600 leading-none tracking-tight uppercase">
            Precise
          </h1>
          <p className="mt-2 text-[13px] font-medium uppercase tracking-[0.34em] text-gray-500">
            Growth Accelerated
          </p>
        </div>

        <p className="text-center text-xl font-semibold text-red-600 mb-6">
          Precise Tender Monitor
        </p>

        <h2 className="text-center text-[27px] font-bold text-gray-950 mb-8">
          Sign in to your account
        </h2>

        <form onSubmit={onSubmit} className="mx-auto max-w-[500px] space-y-6">
          <div>
            <label className="block text-lg font-medium text-gray-900 mb-2">Email address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full h-14 border border-gray-300 rounded-lg px-4 text-lg text-gray-900 placeholder:text-gray-500 shadow-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              required
            />
          </div>

          <div>
            <label className="block text-lg font-medium text-gray-900 mb-2">Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full h-14 border border-gray-300 rounded-lg pl-4 pr-12 text-lg text-gray-900 placeholder:text-gray-500 shadow-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((visible) => !visible)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 transition-colors"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>
          </div>

          <label className="flex items-center gap-3 text-lg text-gray-800">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="h-5 w-5 rounded border-gray-300 text-red-600 focus:ring-red-500 focus:ring-offset-0"
            />
            Remember me
          </label>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full h-14 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white text-lg font-medium rounded-lg transition-colors"
          >
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>

          <div className="text-center pt-1">
            <button
              type="button"
              className="text-base font-medium text-red-600 hover:text-red-700 transition-colors"
            >
              Forgot password?
            </button>
          </div>
        </form>
      </div>

      <p className="mt-8 text-base text-gray-500">© 2026 PRECISE. All rights reserved.</p>
    </div>
  );
};
