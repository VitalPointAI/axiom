'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { 
  Settings, DollarSign, Users, Database, RefreshCw, 
  Loader2, Check, Globe, Clock
} from 'lucide-react';

interface UserPreferences {
  displayCurrency: string;
  timezone?: string;
}

interface AdminStats {
  totalWallets: number;
  totalTransactions: number;
  totalTokens: number;
  lastSync: string | null;
}

interface SyncSettings {
  sync_frequency: string;
  sync_enabled: boolean;
  last_sync: string | null;
  indexer_api: string;
}

const SUPPORTED_CURRENCIES = [
  { code: 'USD', name: 'US Dollar', symbol: '$' },
  { code: 'CAD', name: 'Canadian Dollar', symbol: 'C$' },
  { code: 'EUR', name: 'Euro', symbol: '€' },
  { code: 'GBP', name: 'British Pound', symbol: '£' },
  { code: 'AUD', name: 'Australian Dollar', symbol: 'A$' },
  { code: 'JPY', name: 'Japanese Yen', symbol: '¥' },
  { code: 'CHF', name: 'Swiss Franc', symbol: 'Fr' },
  { code: 'CNY', name: 'Chinese Yuan', symbol: '¥' },
  { code: 'INR', name: 'Indian Rupee', symbol: '₹' },
  { code: 'KRW', name: 'South Korean Won', symbol: '₩' },
  { code: 'BRL', name: 'Brazilian Real', symbol: 'R$' },
  { code: 'MXN', name: 'Mexican Peso', symbol: '$' },
];

const FREQUENCY_OPTIONS = [
  { value: 'hourly', label: 'Every hour' },
  { value: 'every_6h', label: 'Every 6 hours' },
  { value: 'every_12h', label: 'Every 12 hours' },
  { value: 'daily', label: 'Once daily (6am UTC)' },
  { value: 'manual', label: 'Manual only' },
];

export default function AdminPage() {
  const [preferences, setPreferences] = useState<UserPreferences>({ displayCurrency: 'USD' });
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [syncSettings, setSyncSettings] = useState<SyncSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      // Load preferences
      const prefsRes = await fetch('/api/user/preferences');
      if (prefsRes.ok) {
        const data = await prefsRes.json();
        setPreferences(data.preferences || { displayCurrency: 'USD' });
      }

      // Load stats
      const statsRes = await fetch('/api/admin/stats');
      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }

      // Load sync settings
      const syncRes = await fetch('/api/admin/sync');
      if (syncRes.ok) {
        const data = await syncRes.json();
        setSyncSettings(data);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const savePreferences = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const res = await fetch('/api/user/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(preferences),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } catch (error) {
      console.error('Failed to save preferences:', error);
    } finally {
      setSaving(false);
    }
  };

  const updateSyncSettings = async (updates: Partial<SyncSettings>) => {
    try {
      const res = await fetch('/api/admin/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      if (res.ok) {
        setSyncSettings(prev => prev ? { ...prev, ...updates } : prev);
      }
    } catch (error) {
      console.error('Failed to update sync settings:', error);
    }
  };

  const triggerSync = async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const res = await fetch('/api/sync/run', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        setSyncMessage(`Sync complete! ${data.near_txns || 0} NEAR, ${data.ft_txns || 0} FT transactions`);
        await loadData();
      } else {
        setSyncMessage(`Sync failed: ${data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Sync failed:', error);
      setSyncMessage('Sync failed: Network error');
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Admin Settings</h1>
        <p className="text-muted-foreground">Manage your Axiom preferences and data</p>
      </div>

      {/* Stats Overview */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Users className="h-8 w-8 text-blue-500" />
                <div>
                  <div className="text-2xl font-bold">{stats.totalWallets}</div>
                  <p className="text-xs text-muted-foreground">Wallets</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Database className="h-8 w-8 text-green-500" />
                <div>
                  <div className="text-2xl font-bold">{stats.totalTransactions.toLocaleString()}</div>
                  <p className="text-xs text-muted-foreground">Transactions</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <DollarSign className="h-8 w-8 text-purple-500" />
                <div>
                  <div className="text-2xl font-bold">{stats.totalTokens}</div>
                  <p className="text-xs text-muted-foreground">Token Types</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <RefreshCw className="h-8 w-8 text-orange-500" />
                <div>
                  <div className="text-sm font-medium">
                    {stats.lastSync ? new Date(stats.lastSync).toLocaleString() : 'Never'}
                  </div>
                  <p className="text-xs text-muted-foreground">Last Sync</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Sync Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Transaction Sync Settings
          </CardTitle>
          <CardDescription>
            Configure automatic transaction indexing from blockchain APIs
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {syncMessage && (
            <div className={`p-3 rounded ${syncMessage.includes('complete') ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
              {syncMessage}
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {/* Sync Frequency */}
            <div>
              <Label className="text-sm text-muted-foreground">Sync Frequency</Label>
              <select
                value={syncSettings?.sync_frequency || 'every_6h'}
                onChange={(e) => updateSyncSettings({ sync_frequency: e.target.value })}
                className="w-full mt-1 bg-background border border-border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {FREQUENCY_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            {/* Indexer API */}
            <div>
              <Label className="text-sm text-muted-foreground">Transaction API</Label>
              <select
                value={syncSettings?.indexer_api || 'nearblocks'}
                onChange={(e) => updateSyncSettings({ indexer_api: e.target.value })}
                className="w-full mt-1 bg-background border border-border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="nearblocks">NearBlocks (recommended)</option>
                <option value="pikespeak">Pikespeak (legacy)</option>
              </select>
            </div>
          </div>

          {/* Auto-sync Toggle */}
          <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
            <div>
              <div className="font-medium">Auto-sync</div>
              <div className="text-sm text-muted-foreground">Automatically sync transactions on schedule</div>
            </div>
            <button
              onClick={() => updateSyncSettings({ sync_enabled: !syncSettings?.sync_enabled })}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                syncSettings?.sync_enabled ? 'bg-green-600' : 'bg-muted'
              }`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                syncSettings?.sync_enabled ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          </div>

          {/* Manual Sync Button */}
          <Button onClick={triggerSync} disabled={syncing} className="w-full">
            {syncing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Syncing...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4 mr-2" />
                Run Manual Sync Now
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Display Currency */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            Display Currency
          </CardTitle>
          <CardDescription>
            Choose the fiat currency to display alongside token values. 
            Values will be shown in both the token amount and your selected currency.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {SUPPORTED_CURRENCIES.map((currency) => (
                <button
                  key={currency.code}
                  onClick={() => setPreferences({ ...preferences, displayCurrency: currency.code })}
                  className={`p-3 rounded-lg border text-left transition-all ${
                    preferences.displayCurrency === currency.code
                      ? 'border-blue-500 bg-blue-500/10 ring-2 ring-blue-500/20'
                      : 'border-border hover:border-blue-300 hover:bg-muted/50'
                  }`}
                >
                  <div className="font-semibold">{currency.symbol} {currency.code}</div>
                  <div className="text-xs text-muted-foreground">{currency.name}</div>
                </button>
              ))}
            </div>

            <div className="flex items-center gap-3 pt-4">
              <Button onClick={savePreferences} disabled={saving}>
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : saved ? (
                  <Check className="h-4 w-4 mr-2" />
                ) : (
                  <Settings className="h-4 w-4 mr-2" />
                )}
                {saved ? 'Saved!' : 'Save Preferences'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
