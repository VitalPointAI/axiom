'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface CurrencyContextType {
  currency: string;
  setCurrency: (currency: string) => void;
  formatFiat: (usdValue: number) => string;
  convertFromUSD: (usdValue: number) => number;
  symbol: string;
  exchangeRates: Record<string, number>;
  loading: boolean;
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  CAD: 'C$',
  EUR: '€',
  GBP: '£',
  AUD: 'A$',
  JPY: '¥',
  CHF: 'Fr',
  CNY: '¥',
  INR: '₹',
  KRW: '₩',
  BRL: 'R$',
  MXN: '$',
};

const CurrencyContext = createContext<CurrencyContextType | undefined>(undefined);

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setCurrencyState] = useState('USD');
  const [exchangeRates, setExchangeRates] = useState<Record<string, number>>({ USD: 1 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Load user's currency preference
    loadPreferences();
    // Load exchange rates
    loadExchangeRates();
  }, []);

  const loadPreferences = async () => {
    try {
      const res = await fetch('/api/user/preferences');
      if (res.ok) {
        const data = await res.json();
        if (data.preferences?.displayCurrency) {
          setCurrencyState(data.preferences.displayCurrency);
        }
      }
    } catch (error) {
      console.error('Failed to load currency preference:', error);
    }
  };

  const loadExchangeRates = async () => {
    try {
      const res = await fetch('/api/exchange-rates');
      if (res.ok) {
        const data = await res.json();
        setExchangeRates(data.rates || { USD: 1 });
      }
    } catch (error) {
      console.error('Failed to load exchange rates:', error);
      // Fallback rates (approximate)
      setExchangeRates({
        USD: 1,
        CAD: 1.36,
        EUR: 0.92,
        GBP: 0.79,
        AUD: 1.53,
        JPY: 149.5,
        CHF: 0.88,
        CNY: 7.24,
        INR: 83.1,
        KRW: 1320,
        BRL: 4.97,
        MXN: 17.15,
      });
    } finally {
      setLoading(false);
    }
  };

  const setCurrency = async (newCurrency: string) => {
    setCurrencyState(newCurrency);
    // Save to server
    try {
      await fetch('/api/user/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ displayCurrency: newCurrency }),
      });
    } catch (error) {
      console.error('Failed to save currency preference:', error);
    }
  };

  const convertFromUSD = (usdValue: number): number => {
    const rate = exchangeRates[currency] || 1;
    return usdValue * rate;
  };

  const formatFiat = (usdValue: number): string => {
    const converted = convertFromUSD(usdValue);
    const symbol = CURRENCY_SYMBOLS[currency] || currency;
    
    // Format based on currency
    if (currency === 'JPY' || currency === 'KRW') {
      return `${symbol}${Math.round(converted).toLocaleString()}`;
    }
    
    return `${symbol}${converted.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  };

  const symbol = CURRENCY_SYMBOLS[currency] || currency;

  return (
    <CurrencyContext.Provider value={{
      currency,
      setCurrency,
      formatFiat,
      convertFromUSD,
      symbol,
      exchangeRates,
      loading,
    }}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency() {
  const context = useContext(CurrencyContext);
  if (context === undefined) {
    throw new Error('useCurrency must be used within a CurrencyProvider');
  }
  return context;
}

// Helper component for displaying token + fiat values
export function TokenValue({ 
  amount, 
  symbol, 
  usdValue,
  className = '',
}: { 
  amount: number; 
  symbol: string; 
  usdValue?: number;
  className?: string;
}) {
  const { formatFiat } = useCurrency();
  
  return (
    <span className={className}>
      <span className="font-medium">{amount.toLocaleString(undefined, { maximumFractionDigits: 4 })} {symbol}</span>
      {usdValue !== undefined && (
        <span className="text-muted-foreground ml-1">
          ({formatFiat(usdValue)})
        </span>
      )}
    </span>
  );
}
