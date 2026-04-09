'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Settings, Loader2, Check, Globe, HardDrive, AlertTriangle,
  Server, MemoryStick
} from 'lucide-react';

interface UserPreferences {
  displayCurrency: string;
  timezone?: string;
}


interface ContainerInfo {
  name: string;
  service: string;
  status: string;
  state: string;
  health: string;
  cpu: string;
  mem: string;
  mem_pct: string;
  net: string;
}

interface HostStats {
  disk: { total?: string; used?: string; available?: string; use_pct?: string };
  memory: { total?: string; used?: string; available?: string };
}

interface ContainersResponse {
  containers: ContainerInfo[];
  host: HostStats;
}

interface AccountIndexerStatus {
  status: string;
  last_processed_block: number;
  progress_pct: number;
  total_entries: number;
  unique_accounts: number;
  updated_at: string | null;
  stale_seconds: number | null;
  message?: string;
  backfill_info?: string | null;
  backfill_speed?: string | null;
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


export default function AdminPage() {
  const [preferences, setPreferences] = useState<UserPreferences>({ displayCurrency: 'USD' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [indexerStatus, setIndexerStatus] = useState<AccountIndexerStatus | null>(null);
  const [containers, setContainers] = useState<ContainersResponse | null>(null);

  useEffect(() => {
    loadData();
    // Poll account indexer + containers every 30s
    const interval = setInterval(() => {
      loadIndexerStatus();
      loadContainers();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      // Load preferences (may not exist yet)
      try {
        const prefsRes = await fetch('/api/preferences');
        if (prefsRes.ok) {
          const data = await prefsRes.json();
          setPreferences(data.preferences || { displayCurrency: 'USD' });
        }
      } catch { /* endpoint may not exist */ }

      // Load account indexer status + container health
      await loadIndexerStatus();
      await loadContainers();
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadIndexerStatus = async () => {
    try {
      const res = await fetch('/api/admin/account-indexer-status');
      if (res.ok) {
        const data = await res.json();
        setIndexerStatus(data);
      }
    } catch {
      // Silently fail — endpoint may not exist yet
    }
  };

  const loadContainers = async () => {
    try {
      const res = await fetch('/api/admin/containers');
      if (res.ok) {
        const data = await res.json();
        setContainers(data);
      }
    } catch {
      // Silently fail
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
        <h1 className="text-3xl font-bold text-white">Admin Settings</h1>
        <p className="text-gray-400">Manage your Axiom preferences and data</p>
      </div>

      {/* Account Block Index Status */}
      {indexerStatus && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-white">
              <HardDrive className="h-5 w-5" />
              NEAR Account Index
              {indexerStatus.status === 'healthy' && (
                <span className="ml-auto flex items-center gap-1 text-sm font-normal text-green-400">
                  <span className="w-2 h-2 rounded-full bg-green-400" />
                  Healthy
                </span>
              )}
              {indexerStatus.status === 'building' && (
                <span className="ml-auto flex items-center gap-1 text-sm font-normal text-blue-400">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Building Index...
                </span>
              )}
              {indexerStatus.status === 'stale' && (
                <span className="ml-auto flex items-center gap-1 text-sm font-normal text-red-400">
                  <AlertTriangle className="w-3 h-3" />
                  Stale — indexer may be down
                </span>
              )}
              {indexerStatus.status === 'lagging' && (
                <span className="ml-auto flex items-center gap-1 text-sm font-normal text-yellow-400">
                  <AlertTriangle className="w-3 h-3" />
                  Lagging
                </span>
              )}
              {indexerStatus.status === 'not_initialized' && (
                <span className="ml-auto flex items-center gap-1 text-sm font-normal text-gray-400">
                  Not initialized
                </span>
              )}
            </CardTitle>
            <CardDescription>
              Maps NEAR accounts to block heights for instant wallet sync.
              {indexerStatus.status === 'building' && ' Initial backfill in progress — new wallets use fallback scanning until complete.'}
            </CardDescription>
          </CardHeader>
          {indexerStatus.status !== 'not_initialized' && (
            <CardContent className="space-y-4">
              {/* Progress bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Block {indexerStatus.last_processed_block?.toLocaleString()}</span>
                  <span>{indexerStatus.progress_pct}%</span>
                </div>
                <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-1000 rounded-full ${
                      indexerStatus.status === 'healthy' ? 'bg-green-500' :
                      indexerStatus.status === 'stale' ? 'bg-red-500' :
                      'bg-blue-500'
                    }`}
                    style={{ width: `${indexerStatus.progress_pct}%` }}
                  />
                </div>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-muted/50 rounded-lg p-3">
                  <div className="text-lg font-bold">{indexerStatus.total_entries?.toLocaleString()}</div>
                  <div className="text-xs text-muted-foreground">Index Entries</div>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <div className="text-lg font-bold">{indexerStatus.unique_accounts?.toLocaleString()}</div>
                  <div className="text-xs text-muted-foreground">Accounts Indexed</div>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <div className="text-lg font-bold">
                    {indexerStatus.stale_seconds !== null
                      ? indexerStatus.stale_seconds < 60
                        ? `${indexerStatus.stale_seconds}s`
                        : indexerStatus.stale_seconds < 3600
                          ? `${Math.round(indexerStatus.stale_seconds / 60)}m`
                          : `${Math.round(indexerStatus.stale_seconds / 3600)}h`
                      : '—'}
                  </div>
                  <div className="text-xs text-muted-foreground">Last Update</div>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <div className="text-lg font-bold">
                    {indexerStatus.status === 'healthy' ? 'Live' :
                     indexerStatus.status === 'building' ? 'Backfilling' :
                     indexerStatus.status === 'stale' ? 'Down' : 'Catching Up'}
                  </div>
                  <div className="text-xs text-muted-foreground">Mode</div>
                </div>
              </div>

              {indexerStatus.status === 'stale' && !indexerStatus.backfill_info && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>
                    Account indexer hasn&apos;t updated in {Math.round((indexerStatus.stale_seconds || 0) / 60)} minutes.
                    Check if the account-indexer container is running.
                  </span>
                </div>
              )}

              {indexerStatus.backfill_info && (
                <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-sm text-blue-400">
                  <div className="font-medium">{indexerStatus.backfill_info}</div>
                  {indexerStatus.backfill_speed && (
                    <div className="text-xs text-blue-300 mt-1 font-mono">{indexerStatus.backfill_speed}</div>
                  )}
                </div>
              )}
            </CardContent>
          )}
        </Card>
      )}

      {/* System Health — Containers + Host Resources */}
      {containers && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-white">
              <Server className="h-5 w-5" />
              System Health
            </CardTitle>
            <CardDescription>
              Docker containers and server resources
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Host resources */}
            {(containers.host?.disk?.total || containers.host?.memory?.total) && (
              <div className="grid grid-cols-2 gap-3">
                {containers.host?.disk?.total && (
                  <div className="bg-muted/50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <HardDrive className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">Disk</span>
                    </div>
                    <div className="text-sm font-medium">
                      {containers.host?.disk?.used} / {containers.host?.disk?.total}
                    </div>
                    <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden mt-1">
                      <div
                        className={`h-full rounded-full transition-all ${
                          parseInt(containers.host?.disk?.use_pct || '0') > 85
                            ? 'bg-red-500'
                            : parseInt(containers.host?.disk?.use_pct || '0') > 70
                            ? 'bg-yellow-500'
                            : 'bg-green-500'
                        }`}
                        style={{ width: containers.host?.disk?.use_pct || '0%' }}
                      />
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {containers.host?.disk?.available} free
                    </div>
                  </div>
                )}
                {containers.host?.memory?.total && (
                  <div className="bg-muted/50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <MemoryStick className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">Memory</span>
                    </div>
                    <div className="text-sm font-medium">
                      {containers.host?.memory?.used} / {containers.host?.memory?.total}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      {containers.host?.memory?.available} available
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Container list */}
            <div className="border border-gray-700 rounded-md overflow-hidden">
              <div className="grid grid-cols-12 gap-2 px-3 py-2 bg-muted/30 text-xs text-muted-foreground font-medium">
                <div className="col-span-3">Service</div>
                <div className="col-span-2">Status</div>
                <div className="col-span-2">Health</div>
                <div className="col-span-1">CPU</div>
                <div className="col-span-2">Memory</div>
                <div className="col-span-2">Network</div>
              </div>
              {containers.containers.map((c) => (
                <div
                  key={c.name}
                  className="grid grid-cols-12 gap-2 px-3 py-2 border-t border-gray-800 text-xs items-center"
                >
                  <div className="col-span-3 font-medium text-gray-200 truncate">
                    {c.service}
                  </div>
                  <div className="col-span-2">
                    <span className={`inline-flex items-center gap-1 ${
                      c.state === 'running' ? 'text-green-400' :
                      c.state === 'exited' ? 'text-gray-500' : 'text-red-400'
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${
                        c.state === 'running' ? 'bg-green-400' :
                        c.state === 'exited' ? 'bg-gray-500' : 'bg-red-400'
                      }`} />
                      {c.status.split(' ').slice(0, 2).join(' ')}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <span className={`${
                      c.health === 'healthy' ? 'text-green-400' :
                      c.health === 'unhealthy' ? 'text-red-400' :
                      c.health === 'starting' ? 'text-yellow-400' :
                      'text-gray-500'
                    }`}>
                      {c.health === 'none' ? '—' : c.health}
                    </span>
                  </div>
                  <div className="col-span-1 text-gray-400">{c.cpu}</div>
                  <div className="col-span-2 text-gray-400 truncate" title={c.mem}>
                    {c.mem.split(' / ')[0]}
                    <span className="text-gray-600 ml-1">({c.mem_pct})</span>
                  </div>
                  <div className="col-span-2 text-gray-400 truncate" title={c.net}>
                    {c.net}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Display Currency */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-white">
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
