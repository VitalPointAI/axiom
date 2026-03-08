'use client';

import { useState, useEffect } from 'react';
import { 
  UserPlus, 
  Users, 
  Mail, 
  Shield, 
  ShieldCheck, 
  Trash2, 
  Clock, 
  CheckCircle, 
  XCircle,
  Copy,
  ExternalLink,
  RefreshCw
} from 'lucide-react';

interface Invite {
  id: number;
  email: string;
  permission_level: 'read' | 'readwrite';
  status: 'pending' | 'accepted' | 'expired' | 'revoked';
  message: string | null;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
  accepted_by_username: string | null;
}

interface GrantedAccess {
  access_id: number;
  permission_level: 'read' | 'readwrite';
  granted_at: string;
  last_accessed_at: string | null;
  accountant_id: number;
  accountant_username: string;
  accountant_email: string;
}

export function AccountantSettings() {
  const [invites, setInvites] = useState<Invite[]>([]);
  const [grantedAccess, setGrantedAccess] = useState<GrantedAccess[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [invitePermission, setInvitePermission] = useState<'read' | 'readwrite'>('read');
  const [inviteMessage, setInviteMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [lastInviteUrl, setLastInviteUrl] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [invitesRes, accessRes] = await Promise.all([
        fetch('/api/accountant/invite'),
        fetch('/api/accountant/access?view=granted')
      ]);
      
      const invitesData = await invitesRes.json();
      const accessData = await accessRes.json();
      
      setInvites(invitesData.invites || []);
      setGrantedAccess(accessData.granted || []);
    } catch (error) {
      console.error('Failed to fetch accountant data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const sendInvite = async () => {
    if (!inviteEmail) return;
    
    setSending(true);
    try {
      const res = await fetch('/api/accountant/invite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: inviteEmail,
          permissionLevel: invitePermission,
          message: inviteMessage || undefined
        })
      });
      
      const data = await res.json();
      
      if (res.ok) {
        setLastInviteUrl(data.inviteUrl);
        setInviteEmail('');
        setInviteMessage('');
        setShowInviteForm(false);
        fetchData();
      } else {
        alert(data.error || 'Failed to send invitation');
      }
    } catch (error) {
      alert('Failed to send invitation');
    } finally {
      setSending(false);
    }
  };

  const revokeInvite = async (inviteId: number) => {
    if (!confirm('Cancel this invitation?')) return;
    
    try {
      const res = await fetch(`/api/accountant/invite?id=${inviteId}`, { method: 'DELETE' });
      if (res.ok) {
        fetchData();
      }
    } catch (error) {
      alert('Failed to revoke invitation');
    }
  };

  const revokeAccess = async (accessId: number, name: string) => {
    if (!confirm(`Revoke ${name}'s access to your account?`)) return;
    
    try {
      const res = await fetch(`/api/accountant/access?id=${accessId}`, { method: 'DELETE' });
      if (res.ok) {
        fetchData();
      }
    } catch (error) {
      alert('Failed to revoke access');
    }
  };

  const updatePermission = async (accessId: number, newLevel: 'read' | 'readwrite') => {
    try {
      const res = await fetch(`/api/accountant/access?id=${accessId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permissionLevel: newLevel })
      });
      if (res.ok) {
        fetchData();
      }
    } catch (error) {
      alert('Failed to update permission');
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('Copied to clipboard!');
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-200 rounded w-1/3"></div>
          <div className="h-32 bg-slate-200 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Accountant Access</h2>
          <p className="text-sm text-slate-500">
            Invite your accountant or tax professional to view your reports
          </p>
        </div>
        <button
          onClick={() => setShowInviteForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
        >
          <UserPlus className="w-4 h-4" />
          Invite Accountant
        </button>
      </div>

      {/* Last Invite URL (for testing) */}
      {lastInviteUrl && (
        <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-800 font-medium">Invitation sent!</p>
          <div className="flex items-center gap-2 mt-2">
            <input 
              type="text" 
              readOnly 
              value={lastInviteUrl}
              className="flex-1 px-3 py-1.5 text-sm bg-white border rounded"
            />
            <button 
              onClick={() => copyToClipboard(lastInviteUrl)}
              className="p-2 hover:bg-green-100 rounded"
            >
              <Copy className="w-4 h-4" />
            </button>
            <button 
              onClick={() => setLastInviteUrl(null)}
              className="p-2 hover:bg-green-100 rounded"
            >
              <XCircle className="w-4 h-4" />
            </button>
          </div>
          <p className="text-xs text-green-600 mt-1">
            Share this link with your accountant (email sending coming soon)
          </p>
        </div>
      )}

      {/* Invite Form Modal */}
      {showInviteForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
            <h3 className="text-lg font-semibold mb-4">Invite Accountant</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Email Address
                </label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="accountant@example.com"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Permission Level
                </label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="permission"
                      checked={invitePermission === 'read'}
                      onChange={() => setInvitePermission('read')}
                      className="text-blue-600"
                    />
                    <Shield className="w-4 h-4 text-slate-500" />
                    <span className="text-sm">Read Only</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="permission"
                      checked={invitePermission === 'readwrite'}
                      onChange={() => setInvitePermission('readwrite')}
                      className="text-blue-600"
                    />
                    <ShieldCheck className="w-4 h-4 text-green-500" />
                    <span className="text-sm">Read & Write</span>
                  </label>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {invitePermission === 'read' 
                    ? 'Can view reports and download exports'
                    : 'Can also edit categories and add notes'}
                </p>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Personal Message (optional)
                </label>
                <textarea
                  value={inviteMessage}
                  onChange={(e) => setInviteMessage(e.target.value)}
                  placeholder="Hi, I'd like you to review my crypto tax reports..."
                  rows={2}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowInviteForm(false)}
                className="px-4 py-2 text-slate-700 hover:bg-slate-100 rounded-lg transition"
              >
                Cancel
              </button>
              <button
                onClick={sendInvite}
                disabled={!inviteEmail || sending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
              >
                {sending ? 'Sending...' : 'Send Invitation'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Active Access */}
      <div className="bg-white rounded-lg border">
        <div className="p-4 border-b">
          <h3 className="font-medium flex items-center gap-2">
            <Users className="w-5 h-5 text-slate-500" />
            People with Access
          </h3>
        </div>
        
        {grantedAccess.length === 0 ? (
          <div className="p-6 text-center text-slate-500">
            <Shield className="w-8 h-8 mx-auto mb-2 text-slate-300" />
            <p>No one has access to your account yet</p>
          </div>
        ) : (
          <div className="divide-y">
            {grantedAccess.map((access) => (
              <div key={access.access_id} className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-slate-100 rounded-full flex items-center justify-center">
                    <Users className="w-5 h-5 text-slate-500" />
                  </div>
                  <div>
                    <p className="font-medium">{access.accountant_username || access.accountant_email}</p>
                    <p className="text-sm text-slate-500">
                      Granted {new Date(access.granted_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <select
                    value={access.permission_level}
                    onChange={(e) => updatePermission(access.access_id, e.target.value as 'read' | 'readwrite')}
                    className="px-2 py-1 text-sm border rounded"
                  >
                    <option value="read">Read Only</option>
                    <option value="readwrite">Read & Write</option>
                  </select>
                  <button
                    onClick={() => revokeAccess(access.access_id, access.accountant_username || 'this accountant')}
                    className="p-2 text-red-500 hover:bg-red-50 rounded transition"
                    title="Revoke Access"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pending Invitations */}
      <div className="bg-white rounded-lg border">
        <div className="p-4 border-b flex items-center justify-between">
          <h3 className="font-medium flex items-center gap-2">
            <Mail className="w-5 h-5 text-slate-500" />
            Sent Invitations
          </h3>
          <button onClick={fetchData} className="p-1 hover:bg-slate-100 rounded">
            <RefreshCw className="w-4 h-4 text-slate-400" />
          </button>
        </div>
        
        {invites.length === 0 ? (
          <div className="p-6 text-center text-slate-500">
            <Mail className="w-8 h-8 mx-auto mb-2 text-slate-300" />
            <p>No invitations sent yet</p>
          </div>
        ) : (
          <div className="divide-y">
            {invites.map((invite) => (
              <div key={invite.id} className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                    invite.status === 'pending' ? 'bg-amber-100' :
                    invite.status === 'accepted' ? 'bg-green-100' :
                    'bg-slate-100'
                  }`}>
                    {invite.status === 'pending' && <Clock className="w-5 h-5 text-amber-600" />}
                    {invite.status === 'accepted' && <CheckCircle className="w-5 h-5 text-green-600" />}
                    {(invite.status === 'expired' || invite.status === 'revoked') && 
                      <XCircle className="w-5 h-5 text-slate-400" />}
                  </div>
                  <div>
                    <p className="font-medium">{invite.email}</p>
                    <p className="text-sm text-slate-500">
                      {invite.status === 'pending' && `Expires ${new Date(invite.expires_at).toLocaleDateString()}`}
                      {invite.status === 'accepted' && `Accepted by ${invite.accepted_by_username}`}
                      {invite.status === 'expired' && 'Expired'}
                      {invite.status === 'revoked' && 'Cancelled'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 text-xs rounded-full ${
                    invite.permission_level === 'read' 
                      ? 'bg-slate-100 text-slate-600' 
                      : 'bg-green-100 text-green-700'
                  }`}>
                    {invite.permission_level === 'read' ? 'Read' : 'Read/Write'}
                  </span>
                  {invite.status === 'pending' && (
                    <button
                      onClick={() => revokeInvite(invite.id)}
                      className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition"
                      title="Cancel Invitation"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
