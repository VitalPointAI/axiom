-- Auto-fix stuck syncs: if syncing for > 30 minutes, reset to pending
-- Run this periodically via cron or add to sync API

UPDATE wallets 
SET sync_status = 'pending', 
    last_synced_at = NOW()
WHERE sync_status = 'syncing' 
  AND (
    last_synced_at IS NULL 
    OR last_synced_at < NOW() - INTERVAL '30 minutes'
  );

-- Mark unsupported chains as complete if stuck in pending > 1 day
UPDATE wallets 
SET sync_status = 'complete'
WHERE sync_status = 'pending'
  AND chain IN ('AKASH', 'XRP', 'CRONOS')
  AND created_at < NOW() - INTERVAL '1 day';
