import { useState } from 'react';
import { Button } from '@/components/ui';

export interface SyncOptions {
  start_date?: string;
  end_date?: string;
  download_fit?: boolean;
  max_activities?: number;
}

const COMPACT_INPUT =
  'w-full bg-shadow border border-text-muted/30 rounded px-2 py-1 text-text-primary font-mono';

export function SyncOptionsForm({
  onSync,
  isLoading,
}: {
  onSync: (options: SyncOptions) => void;
  isLoading: boolean;
}) {
  const [days, setDays] = useState(30);
  const [downloadFit, setDownloadFit] = useState(true);
  const [maxActivities, setMaxActivities] = useState(50);

  const handleSync = () => {
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);
    onSync({
      start_date: startDate.toISOString().split('T')[0],
      download_fit: downloadFit,
      max_activities: maxActivities,
    });
  };

  return (
    <div className="p-3 rounded border border-text-muted/20">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <label className="text-xs text-text-muted font-mono block mb-1">Date range</label>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={COMPACT_INPUT}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-text-muted font-mono block mb-1">Max activities</label>
          <input
            type="number"
            value={maxActivities}
            onChange={(e) => setMaxActivities(Number(e.target.value))}
            className={COMPACT_INPUT}
          />
        </div>
        <div className="col-span-2 flex items-center gap-2">
          <input
            type="checkbox"
            id="systemDownloadFit"
            checked={downloadFit}
            onChange={(e) => setDownloadFit(e.target.checked)}
            className="accent-neon-cyan"
          />
          <label htmlFor="systemDownloadFit" className="text-xs text-text-muted font-mono">
            Download FIT files
          </label>
        </div>
      </div>
      <Button fullWidth className="mt-3" onClick={handleSync} loading={isLoading}>
        {isLoading ? 'SYNCING...' : '[START SYNC]'}
      </Button>
    </div>
  );
}
