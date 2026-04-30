import React, { useEffect, useState } from 'react';
import { KeyRound, Lock, User as UserIcon, UserPlus } from 'lucide-react';
import { apiService, AuthUser } from '../services/api';

interface AccountPageProps {
  user: AuthUser;
  onUserUpdated: (user: AuthUser) => void;
}

export const AccountPage: React.FC<AccountPageProps> = ({ user, onUserUpdated }) => {
  const [fullName, setFullName] = useState(user.full_name ?? '');
  const [profileMessage, setProfileMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);

  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordMessage, setPasswordMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [passwordSaving, setPasswordSaving] = useState(false);

  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteFullName, setInviteFullName] = useState('');
  const [invitePassword, setInvitePassword] = useState('');
  const [inviteRole, setInviteRole] = useState<'viewer' | 'analyst' | 'admin'>('viewer');
  const [inviteMessage, setInviteMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [inviteSaving, setInviteSaving] = useState(false);

  const [resetEmail, setResetEmail] = useState('');
  const [resetNewPassword, setResetNewPassword] = useState('');
  const [resetConfirmPassword, setResetConfirmPassword] = useState('');
  const [resetMessage, setResetMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [resetSaving, setResetSaving] = useState(false);

  useEffect(() => {
    setFullName(user.full_name ?? '');
  }, [user.full_name, user.id]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileMessage(null);
    setProfileSaving(true);
    try {
      const updated = await apiService.updateProfile({ full_name: fullName.trim() || null });
      onUserUpdated(updated);
      setProfileMessage({ type: 'ok', text: 'Profile saved.' });
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setProfileMessage({ type: 'err', text: typeof d === 'string' ? d : 'Could not save profile.' });
    } finally {
      setProfileSaving(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordMessage(null);
    if (newPassword.length < 8) {
      setPasswordMessage({ type: 'err', text: 'New password must be at least 8 characters.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordMessage({ type: 'err', text: 'New passwords do not match.' });
      return;
    }
    setPasswordSaving(true);
    try {
      await apiService.changePassword(oldPassword, newPassword);
      setPasswordMessage({ type: 'ok', text: 'Password updated.' });
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPasswordMessage({ type: 'err', text: typeof d === 'string' ? d : 'Could not update password.' });
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleInviteUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteMessage(null);
    setInviteSaving(true);
    try {
      await apiService.createCompanyUser({
        email: inviteEmail.trim(),
        password: invitePassword,
        full_name: inviteFullName.trim() || undefined,
        role: inviteRole,
      });
      setInviteMessage({
        type: 'ok',
        text: 'User created. Share the password securely (no invitation email is sent yet).',
      });
      setInviteEmail('');
      setInviteFullName('');
      setInvitePassword('');
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setInviteMessage({ type: 'err', text: typeof d === 'string' ? d : 'Could not create user.' });
    } finally {
      setInviteSaving(false);
    }
  };

  const handleResetOtherPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setResetMessage(null);
    if (!resetEmail.trim()) {
      setResetMessage({ type: 'err', text: 'Enter the user\'s email.' });
      return;
    }
    if (resetNewPassword.length < 8) {
      setResetMessage({ type: 'err', text: 'New password must be at least 8 characters.' });
      return;
    }
    if (resetNewPassword !== resetConfirmPassword) {
      setResetMessage({ type: 'err', text: 'New passwords do not match.' });
      return;
    }
    setResetSaving(true);
    try {
      const result = await apiService.adminSetUserPassword(resetEmail.trim(), resetNewPassword);
      setResetMessage({ type: 'ok', text: result.message || 'Password updated.' });
      setResetNewPassword('');
      setResetConfirmPassword('');
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setResetMessage({
        type: 'err',
        text: typeof d === 'string' ? d : 'Could not update password for this user.',
      });
    } finally {
      setResetSaving(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Account</h2>
        <p className="mt-1 text-sm text-gray-600">
          Update how your name appears and manage your password. Role:{' '}
          <span className="font-medium text-gray-800">{user.role}</span>
        </p>
      </div>

      <section className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-3">
          <UserIcon className="h-5 w-5 text-slate-600 shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Profile</h3>
            <p className="text-xs text-gray-500">Your email cannot be changed here.</p>
          </div>
        </div>
        <form onSubmit={handleSaveProfile} className="p-6 space-y-4">
          <div>
            <label htmlFor="account-email" className="block text-xs font-medium text-gray-700 uppercase tracking-wide mb-1">
              Email
            </label>
            <input
              id="account-email"
              type="email"
              value={user.email}
              readOnly
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50 text-gray-600 cursor-not-allowed"
            />
          </div>
          <div>
            <label htmlFor="account-full-name" className="block text-xs font-medium text-gray-700 uppercase tracking-wide mb-1">
              Display name
            </label>
            <input
              id="account-full-name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your full name"
              autoComplete="name"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          {profileMessage && (
            <p className={`text-sm ${profileMessage.type === 'ok' ? 'text-green-700' : 'text-red-600'}`}>
              {profileMessage.text}
            </p>
          )}
          <button
            type="submit"
            disabled={profileSaving}
            className="inline-flex justify-center px-4 py-2 text-sm font-medium text-white bg-slate-800 rounded-lg hover:bg-slate-900 disabled:opacity-50"
          >
            {profileSaving ? 'Saving…' : 'Save profile'}
          </button>
        </form>
      </section>

      <section className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-3">
          <Lock className="h-5 w-5 text-slate-600 shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Password</h3>
            <p className="text-xs text-gray-500">Use a strong password you do not reuse elsewhere.</p>
          </div>
        </div>
        <form onSubmit={handleChangePassword} className="p-6 space-y-3">
          <input
            type="password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            placeholder="Current password"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            autoComplete="current-password"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New password (min 8 characters)"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            autoComplete="new-password"
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Confirm new password"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            autoComplete="new-password"
          />
          {passwordMessage && (
            <p className={`text-sm ${passwordMessage.type === 'ok' ? 'text-green-700' : 'text-red-600'}`}>
              {passwordMessage.text}
            </p>
          )}
          <button
            type="submit"
            disabled={passwordSaving}
            className="inline-flex justify-center px-4 py-2 text-sm font-medium text-white bg-slate-800 rounded-lg hover:bg-slate-900 disabled:opacity-50"
          >
            {passwordSaving ? 'Updating…' : 'Update password'}
          </button>
        </form>
      </section>

      {user.role === 'super_admin' && (
        <section className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-3">
            <KeyRound className="h-5 w-5 text-amber-700 shrink-0" />
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Reset another user&apos;s password</h3>
              <p className="text-xs text-gray-500">
                When someone forgot their password, set a new temporary password here and share it securely outside the app.
              </p>
            </div>
          </div>
          <form onSubmit={handleResetOtherPassword} className="p-6 space-y-3">
            <input
              type="email"
              value={resetEmail}
              onChange={(e) => setResetEmail(e.target.value)}
              placeholder={"User's company email"}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              autoComplete="off"
            />
            <input
              type="password"
              value={resetNewPassword}
              onChange={(e) => setResetNewPassword(e.target.value)}
              placeholder="New password (min 8 characters)"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              autoComplete="new-password"
            />
            <input
              type="password"
              value={resetConfirmPassword}
              onChange={(e) => setResetConfirmPassword(e.target.value)}
              placeholder="Confirm new password"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              autoComplete="new-password"
            />
            {resetMessage && (
              <p className={`text-sm ${resetMessage.type === 'ok' ? 'text-green-700' : 'text-red-600'}`}>
                {resetMessage.text}
              </p>
            )}
            <button
              type="submit"
              disabled={
                resetSaving ||
                !resetEmail.trim() ||
                resetNewPassword.length < 8 ||
                resetNewPassword !== resetConfirmPassword
              }
              className="inline-flex justify-center px-4 py-2 text-sm font-medium text-white bg-amber-700 rounded-lg hover:bg-amber-800 disabled:opacity-50"
            >
              {resetSaving ? 'Updating…' : 'Set password for user'}
            </button>
          </form>
        </section>
      )}

      {user.role === 'super_admin' && (
        <section className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-3">
            <UserPlus className="h-5 w-5 text-blue-600 shrink-0" />
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Add company user</h3>
              <p className="text-xs text-gray-500">Allowed company domains only. Password is not emailed — share it securely.</p>
            </div>
          </div>
          <form onSubmit={handleInviteUser} className="p-6 space-y-3">
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="name@company.com"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <input
              type="text"
              value={inviteFullName}
              onChange={(e) => setInviteFullName(e.target.value)}
              placeholder="Full name (optional)"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <input
              type="password"
              value={invitePassword}
              onChange={(e) => setInvitePassword(e.target.value)}
              placeholder="Temporary password (min 8 characters)"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as 'viewer' | 'analyst' | 'admin')}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="viewer">viewer</option>
              <option value="analyst">analyst</option>
              <option value="admin">admin</option>
            </select>
            {inviteMessage && (
              <p className={`text-sm ${inviteMessage.type === 'ok' ? 'text-green-700' : 'text-red-600'}`}>
                {inviteMessage.text}
              </p>
            )}
            <button
              type="submit"
              disabled={inviteSaving || !inviteEmail.trim() || invitePassword.length < 8}
              className="inline-flex justify-center px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {inviteSaving ? 'Creating…' : 'Create user'}
            </button>
          </form>
        </section>
      )}

      <p className="text-xs text-gray-500 leading-relaxed">
        Forgot your password? Contact a super admin to reset it or give you a new temporary password.
        Self-service email reset is not set up yet.
      </p>
    </div>
  );
};
