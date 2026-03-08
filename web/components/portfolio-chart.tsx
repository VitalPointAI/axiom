'use client';

import { useEffect, useState } from 'react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer 
} from 'recharts';
import { TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';

interface ApiHistoryPoint {
  date: string;
  totalNear: number;
  nearPrice: number;
  totalValueUsd: number;
}

interface PortfolioHistoryData {
  history: ApiHistoryPoint[];
  currentValue: number;
  currentNear: number;
  breakdown?: {
    liquid: number;
    staked: number;
    nearPrice: number;
  };
}

export function PortfolioChart() {
  const [data, setData] = useState<PortfolioHistoryData | null>(null);
  const [liveValue, setLiveValue] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<'30d' | '90d' | '1y'>('90d');

  const fetchData = async () => {
    try {
      setLoading(true);
      
      // Fetch both history and live portfolio in parallel
      const [histRes, liveRes] = await Promise.all([
        fetch('/api/portfolio/history'),
        fetch('/api/portfolio')
      ]);
      
      if (!histRes.ok) throw new Error('Failed to fetch history');
      const histJson = await histRes.json();
      setData(histJson);
      
      // Get live value to ensure chart endpoint matches card
      if (liveRes.ok) {
        const liveJson = await liveRes.json();
        setLiveValue(liveJson.totalValue || null);
      }
      
      setError(null);
    } catch (err) {
      setError('Failed to load history');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6 animate-pulse">
        <div className="h-6 bg-slate-200 rounded w-1/3 mb-4"></div>
        <div className="h-48 bg-slate-200 rounded"></div>
      </div>
    );
  }

  if (error || !data || !data.history) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <p className="text-red-500">{error || 'No data available'}</p>
        <button onClick={fetchData} className="mt-2 text-sm text-blue-500 hover:underline">
          Retry
        </button>
      </div>
    );
  }

  // Filter by time range
  const now = new Date();
  const cutoff = new Date();
  if (timeRange === '30d') cutoff.setDate(now.getDate() - 30);
  else if (timeRange === '90d') cutoff.setDate(now.getDate() - 90);
  else cutoff.setFullYear(now.getFullYear() - 1);
  
  const filteredHistory = data.history.filter(h => new Date(h.date) >= cutoff);

  // Use live value for current, fall back to API currentValue, then last history point
  const currentValue = liveValue ?? data.currentValue ?? (filteredHistory.length > 0 ? filteredHistory[filteredHistory.length - 1].totalValueUsd : 0);
  
  // Start value from history
  const startValue = filteredHistory.length > 0 ? (filteredHistory[0].totalValueUsd || 0) : 0;
  
  const change = currentValue - startValue;
  const changePercent = startValue > 0 ? ((currentValue - startValue) / startValue) * 100 : 0;
  const isPositive = change >= 0;

  // Format data for chart - inject current live value as today's point
  const chartData = filteredHistory.map(h => ({
    date: h.date,
    value: Math.round(h.totalValueUsd || 0),
    near: h.totalNear || 0,
    label: new Date(h.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }));

  // If the last point isn't today, add today with the current value
  const today = new Date().toISOString().split('T')[0];
  const lastDate = chartData.length > 0 ? chartData[chartData.length - 1].date : null;
  if (lastDate !== today && currentValue > 0) {
    chartData.push({
      date: today,
      value: Math.round(currentValue),
      near: data.currentNear || 0,
      label: new Date(today).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    });
  } else if (chartData.length > 0) {
    // Update the last point with live value to ensure consistency
    chartData[chartData.length - 1].value = Math.round(currentValue);
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-700">Portfolio History</h2>
          <div className="flex items-center gap-2 mt-1">
            {isPositive ? (
              <TrendingUp className="w-4 h-4 text-green-500" />
            ) : (
              <TrendingDown className="w-4 h-4 text-red-500" />
            )}
            <span className={isPositive ? 'text-green-600' : 'text-red-600'}>
              {isPositive ? '+' : ''}${Math.abs(change).toLocaleString(undefined, { maximumFractionDigits: 0 })}
              {' '}({isPositive ? '+' : ''}{changePercent.toFixed(1)}%)
            </span>
            <span className="text-slate-400 text-sm">
              {timeRange === '30d' ? '30 days' : timeRange === '90d' ? '90 days' : '1 year'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-slate-100 rounded-lg p-1">
            {(['30d', '90d', '1y'] as const).map(range => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1 text-sm rounded-md transition ${
                  timeRange === range 
                    ? 'bg-white shadow text-slate-900' 
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {range === '1y' ? '1Y' : range.toUpperCase()}
              </button>
            ))}
          </div>
          <button 
            onClick={fetchData}
            className="p-2 hover:bg-slate-100 rounded-lg transition"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-slate-400" />
          </button>
        </div>
      </div>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis 
              dataKey="label" 
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: '#94a3b8' }}
              interval="preserveStartEnd"
            />
            <YAxis 
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: '#94a3b8' }}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              width={50}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'white', 
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                fontSize: '12px'
              }}
              formatter={(value: number) => [
                `$${value.toLocaleString()}`,
                'Value'
              ]}
              labelFormatter={(label) => label}
            />
            <Area 
              type="monotone" 
              dataKey="value" 
              stroke={isPositive ? '#10b981' : '#ef4444'}
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorValue)" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="flex justify-between mt-4 pt-4 border-t text-sm text-slate-500">
        <div>
          Start: <span className="text-slate-700 font-medium">${startValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
        </div>
        <div>
          Current: <span className="text-slate-700 font-medium">${currentValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
        </div>
      </div>
    </div>
  );
}
