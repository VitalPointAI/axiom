'use client';

import { useState, useRef, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { 
  MessageCircle, 
  X, 
  Send, 
  Loader2,
  Sparkles,
  HelpCircle,
  Calculator
} from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface TallyProps {
  pageContext?: Record<string, any>;
}

const PAGE_CONTEXTS: Record<string, string> = {
  '/dashboard': 'The main dashboard showing portfolio overview, total holdings value, and recent activity summary.',
  '/dashboard/wallets': 'Wallet management page where users add and manage their crypto wallets across different chains (NEAR, Ethereum, etc.).',
  '/dashboard/assets': 'Assets overview showing all token holdings across all chains with current USD values and portfolio allocation.',
  '/dashboard/transactions': 'Transaction history page with all crypto transactions, filterable by asset, chain, type, date, and tax category.',
  '/dashboard/staking': 'Staking income tracker showing validator rewards, deposits, withdrawals, and earned interest over time.',
  '/dashboard/defi': 'DeFi activity page tracking lending, borrowing, liquidity provision, and yield farming across protocols like Burrow, Ref Finance, and Meta Pool.',
  '/dashboard/exchanges': 'Exchange connections page for linking centralized exchanges like Coinbase and Crypto.com to import transaction history.',
  '/dashboard/reports': 'Tax reports page for generating Schedule 3 (capital gains), T1135 (foreign property), income reports, and other tax documents for Canadian filing.',
  '/dashboard/prices': 'Price warnings page highlighting transactions with missing or potentially incorrect historical prices that may affect tax calculations.',
  '/dashboard/settings': 'Settings page for managing accountant access and sharing reports with tax professionals.',
  '/dashboard/admin': 'Admin page for system configuration, sync settings, and indexer management.',
  '/dashboard/swap': 'Token swap interface for exchanging cryptocurrencies directly within Axiom.',
};

const QUICK_QUESTIONS = [
  "What is this page for?",
  "How do I categorize transactions?",
  "What's a taxable event?",
  "How do staking rewards work?",
];

export function Tally({ pageContext }: TallyProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pathname = usePathname();

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const getPageContext = () => {
    const baseContext = PAGE_CONTEXTS[pathname] || 'A page in Axiom crypto tax reporting software.';
    
    let context = `Current page: ${pathname}\n${baseContext}`;
    
    if (pageContext) {
      if (pageContext.totalValue) {
        context += `\nTotal portfolio value: $${pageContext.totalValue.toLocaleString()}`;
      }
      if (pageContext.assetCount) {
        context += `\nNumber of assets: ${pageContext.assetCount}`;
      }
      if (pageContext.transactionCount) {
        context += `\nTransactions shown: ${pageContext.transactionCount}`;
      }
      if (pageContext.selectedFilters) {
        context += `\nActive filters: ${JSON.stringify(pageContext.selectedFilters)}`;
      }
    }
    
    return context;
  };

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMessage = { role: 'user' as const, content: text };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/tally', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          pageContext: getPageContext(),
          history: messages.slice(-6), // Last 3 exchanges
        }),
      });

      const data = await res.json();
      
      if (data.response) {
        setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
      } else {
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: "Sorry, I couldn't process that request. Please try again!" 
        }]);
      }
    } catch (error) {
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: "Oops! Something went wrong. Please try again." 
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-300 ${
          isOpen 
            ? 'bg-slate-700 rotate-0' 
            : 'bg-gradient-to-br from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 hover:scale-110'
        }`}
        title={isOpen ? 'Close Tally' : 'Ask Tally'}
      >
        {isOpen ? (
          <X className="w-6 h-6 text-white" />
        ) : (
          <div className="relative">
            <Calculator className="w-6 h-6 text-white" />
            <Sparkles className="w-3 h-3 text-yellow-300 absolute -top-1 -right-1" />
          </div>
        )}
      </button>

      {/* Chat Panel */}
      {isOpen && (
        <div className="fixed bottom-24 right-6 z-50 w-96 max-w-[calc(100vw-3rem)] bg-slate-900 rounded-2xl shadow-2xl border border-slate-700 flex flex-col overflow-hidden animate-in slide-in-from-bottom-4 duration-300">
          {/* Header */}
          <div className="bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-3 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
              <Calculator className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-white">Tally</h3>
              <p className="text-xs text-emerald-100">Your crypto tax assistant</p>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 hover:bg-white/10 rounded-lg transition"
            >
              <X className="w-5 h-5 text-white" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 max-h-96 min-h-[200px] bg-slate-850">
            {messages.length === 0 ? (
              <div className="text-center py-6">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-emerald-500/20 to-teal-500/20 flex items-center justify-center">
                  <HelpCircle className="w-8 h-8 text-emerald-400" />
                </div>
                <p className="text-slate-400 text-sm mb-4">
                  Hi! I'm Tally, your crypto tax assistant. Ask me anything about this page or how Axiom works!
                </p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {QUICK_QUESTIONS.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(q)}
                      className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-full transition"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] px-4 py-2 rounded-2xl ${
                      msg.role === 'user'
                        ? 'bg-emerald-600 text-white rounded-br-md'
                        : 'bg-slate-800 text-slate-200 rounded-bl-md'
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              ))
            )}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-slate-800 px-4 py-3 rounded-2xl rounded-bl-md">
                  <Loader2 className="w-5 h-5 text-emerald-400 animate-spin" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <form onSubmit={handleSubmit} className="p-3 border-t border-slate-700 bg-slate-800">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask Tally anything..."
                className="flex-1 px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-full text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-sm"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="w-10 h-10 rounded-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:cursor-not-allowed flex items-center justify-center transition"
              >
                <Send className="w-4 h-4 text-white" />
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
