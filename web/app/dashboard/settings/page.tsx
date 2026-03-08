'use client';

import { AccountantSettings } from '@/components/accountant-settings';
import { IndexerStatus } from '@/components/indexer-status';

export default function SettingsPage() {
  return (
    <div className="max-w-6xl mx-auto py-8 px-4 space-y-8">
      {/* Indexer Status */}
      <IndexerStatus />
      
      {/* Accountant Settings */}
      <AccountantSettings />
    </div>
  );
}
