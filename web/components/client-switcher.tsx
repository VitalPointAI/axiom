'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { 
  Users, 
  ChevronDown, 
  Eye, 
  LogOut, 
  Check,
  Building2,
  Wallet,
  ShieldCheck,
  ShieldAlert
} from 'lucide-react';

interface Client {
  id: number;
  nearAccountId: string;
  name: string;
  permissionLevel: 'read' | 'readwrite';
  walletCount: number;
  lastAccessed: string | null;
}

interface ViewingStatus {
  ownAccount: {
    id: number;
    nearAccountId: string;
    username: string | null;
  };
  isAccountant: boolean;
  clients: Client[];
  currentlyViewing: Client | null;
}

export function ClientSwitcher() {
  const [status, setStatus] = useState<ViewingStatus | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    fetchStatus();
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/accountant/switch');
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (error) {
      console.error('Failed to fetch viewing status:', error);
    } finally {
      setLoading(false);
    }
  };

  const switchToClient = async (clientId: number) => {
    setSwitching(true);
    try {
      const res = await fetch('/api/accountant/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clientId }),
      });
      
      if (res.ok) {
        setIsOpen(false);
        // Refresh the page to load client's data
        router.refresh();
        window.location.reload();
      }
    } catch (error) {
      console.error('Failed to switch client:', error);
    } finally {
      setSwitching(false);
    }
  };

  const exitClientView = async () => {
    setSwitching(true);
    try {
      const res = await fetch('/api/accountant/switch', {
        method: 'DELETE',
      });
      
      if (res.ok) {
        setIsOpen(false);
        router.refresh();
        window.location.reload();
      }
    } catch (error) {
      console.error('Failed to exit client view:', error);
    } finally {
      setSwitching(false);
    }
  };

  // Don't render if not an accountant or still loading
  if (loading || !status?.isAccountant) {
    return null;
  }

  const isViewing = !!status.currentlyViewing;

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Viewing indicator banner */}
      {isViewing && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500 text-amber-950 py-1 px-4 text-center text-sm font-medium flex items-center justify-center gap-2">
          <Eye className="w-4 h-4" />
          <span>
            Viewing as: <strong>{status.currentlyViewing?.name}</strong>
            {status.currentlyViewing?.permissionLevel === 'read' && (
              <span className="ml-2 text-amber-800">(Read-only)</span>
            )}
          </span>
          <button
            onClick={exitClientView}
            disabled={switching}
            className="ml-4 px-2 py-0.5 bg-amber-600 hover:bg-amber-700 rounded text-white text-xs font-medium transition"
          >
            Exit View
          </button>
        </div>
      )}

      {/* Switcher button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition ${
          isViewing 
            ? 'bg-amber-500/20 text-amber-400 hover:bg-amber-500/30' 
            : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
        }`}
      >
        <Users className="w-4 h-4" />
        <span className="text-sm hidden sm:inline">
          {isViewing ? status.currentlyViewing?.name : 'Clients'}
        </span>
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 bg-slate-800 border border-slate-700 rounded-xl shadow-xl z-50 overflow-hidden">
          {/* Own account option */}
          <div className="p-2 border-b border-slate-700">
            <button
              onClick={exitClientView}
              disabled={!isViewing || switching}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition ${
                !isViewing 
                  ? 'bg-emerald-500/20 text-emerald-400' 
                  : 'text-slate-300 hover:bg-slate-700'
              }`}
            >
              <Building2 className="w-5 h-5" />
              <div className="flex-1 text-left">
                <div className="font-medium text-sm">My Account</div>
                <div className="text-xs text-slate-400 truncate">
                  {status.ownAccount.nearAccountId}
                </div>
              </div>
              {!isViewing && <Check className="w-4 h-4 text-emerald-400" />}
            </button>
          </div>

          {/* Client list */}
          <div className="p-2 max-h-64 overflow-y-auto">
            <div className="text-xs font-medium text-slate-500 px-3 py-1 mb-1">
              CLIENT ACCOUNTS ({status.clients.length})
            </div>
            {status.clients.map((client) => (
              <button
                key={client.id}
                onClick={() => switchToClient(client.id)}
                disabled={switching || (isViewing && status.currentlyViewing?.id === client.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition ${
                  isViewing && status.currentlyViewing?.id === client.id
                    ? 'bg-amber-500/20 text-amber-400'
                    : 'text-slate-300 hover:bg-slate-700'
                }`}
              >
                {client.permissionLevel === 'readwrite' ? (
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                ) : (
                  <ShieldAlert className="w-5 h-5 text-amber-400" />
                )}
                <div className="flex-1 text-left min-w-0">
                  <div className="font-medium text-sm truncate">{client.name}</div>
                  <div className="text-xs text-slate-400 flex items-center gap-2">
                    <Wallet className="w-3 h-3" />
                    {client.walletCount} wallet{client.walletCount !== 1 ? 's' : ''}
                    <span className="text-slate-500">•</span>
                    {client.permissionLevel === 'read' ? 'Read' : 'Full'}
                  </div>
                </div>
                {isViewing && status.currentlyViewing?.id === client.id && (
                  <Check className="w-4 h-4 text-amber-400" />
                )}
              </button>
            ))}
          </div>

          {/* Exit button when viewing */}
          {isViewing && (
            <div className="p-2 border-t border-slate-700">
              <button
                onClick={exitClientView}
                disabled={switching}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition"
              >
                <LogOut className="w-4 h-4" />
                <span className="text-sm">Exit Client View</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
