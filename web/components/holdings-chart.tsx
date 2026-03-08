'use client';

import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

interface Holding {
  asset: string;
  symbol?: string;
  amount: number;
  chain: string;
  price: number;
  value: number;
}

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#84CC16'];

export function HoldingsChart() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/portfolio')
      .then(res => res.json())
      .then(data => {
        // Filter and sanitize holdings
        const validHoldings = (data.holdings || [])
          .filter((h: any) => h && typeof h.value === 'number' && h.value > 0.01)
          .map((h: any) => ({
            asset: h.asset || h.symbol || 'Unknown',
            amount: h.amount ?? 0,
            chain: h.chain || 'NEAR',
            price: h.price ?? 0,
            value: h.value ?? 0
          }));
        setHoldings(validHoldings);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-4">Holdings</h2>
        <div className="h-64 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-400"></div>
        </div>
      </div>
    );
  }

  if (holdings.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-4">Holdings</h2>
        <div className="h-64 flex flex-col items-center justify-center text-slate-500">
          <p>No holdings yet</p>
          <p className="text-sm">Add a wallet to see your assets</p>
        </div>
      </div>
    );
  }

  const chartData = holdings.slice(0, 8).map(h => ({
    name: h.asset,
    value: h.value,
  }));

  const totalValue = holdings.reduce((sum, h) => sum + (h.value || 0), 0);

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      <h2 className="text-lg font-semibold text-slate-700 mb-4">Holdings ({holdings.length} assets)</h2>
      
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={80}
              paddingAngle={2}
              dataKey="value"
            >
              {chartData.map((_, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip 
              formatter={(value: number) => [`$${(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`, 'Value']}
            />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 space-y-2 max-h-48 overflow-y-auto">
        {holdings.slice(0, 15).map((holding, index) => (
          <div key={holding.asset + index} className="flex items-center justify-between py-2 border-b last:border-0">
            <div className="flex items-center gap-2">
              <div 
                className="w-3 h-3 rounded-full" 
                style={{ backgroundColor: COLORS[index % COLORS.length] }}
              />
              <span className="font-medium text-slate-700">{holding.asset}</span>
            </div>
            <div className="text-right">
              <p className="font-medium text-slate-900">
                ${(holding.value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
              <p className="text-xs text-slate-500">
                {(holding.amount || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })} {holding.asset}
              </p>
              {totalValue > 0 && (
                <p className="text-xs text-slate-400">
                  {(((holding.value || 0) / totalValue) * 100).toFixed(1)}%
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
