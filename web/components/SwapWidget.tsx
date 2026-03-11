"use client";

import { useState, Component, ReactNode } from "react";
import {
  type WidgetConfig,
  type Theme,
  WidgetConfigProvider,
  Widget,
} from "@aurora-is-near/intents-swap-widget";
import "@aurora-is-near/intents-swap-widget/styles.css";
import "@aurora-is-near/intents-swap-widget/theme.css";
import { useAuth } from "./auth-provider";
import { useRouter } from "next/navigation";

// Error boundary to catch widget crashes
class WidgetErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode; fallback: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error('Swap widget error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

export function SwapWidget() {
  const { user, signOut, isLoading } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [widgetReady, setWidgetReady] = useState(false);

  const handleConnect = () => {
    router.push('/auth');
  };

  const widgetConfig: Partial<WidgetConfig> = {
    appName: "Axiom",
    connectedWallets: user?.nearAccountId ? { 
      default: user.nearAccountId, 
      near: user.nearAccountId 
    } : {},
    slippageTolerance: 50,
    enableAccountAbstraction: true,
    showProfileButton: false,
    chainsOrder: ["near", "eth", "arb", "base"],
    appFees: [
      {
        recipient: "vitalpointai.near",
        fee: 300, // 3% = 300 basis points
      },
    ],
    onWalletSignin: handleConnect,
    onWalletSignout: signOut,
  };

  const theme: Theme = {
    colorScheme: "dark",
    stylePreset: "clean",
    borderRadius: "md",
    accentColor: "#3B82F6",
    backgroundColor: "#1e293b",
    successColor: "#10B981",
    warningColor: "#F59E0B",
    errorColor: "#EF4444",
  };

  if (isLoading) {
    return (
      <div className="bg-slate-800 rounded-xl p-8 border border-slate-700 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3" />
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  const widgetFallback = (
    <div className="p-8 text-center">
      <p className="text-amber-400 mb-2">Swap widget failed to load</p>
      <p className="text-gray-500 text-sm">Please refresh the page or try again later.</p>
      <button 
        onClick={() => window.location.reload()}
        className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition"
      >
        Refresh Page
      </button>
    </div>
  );

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      {/* Connection status header */}
      <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
        {user ? (
          <>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-sm text-gray-300">
                {user.codename || (user.nearAccountId.length > 24 
                  ? `${user.nearAccountId.slice(0, 12)}...${user.nearAccountId.slice(-8)}`
                  : user.nearAccountId)}
              </span>
            </div>
            <button 
              onClick={signOut}
              className="text-xs text-red-400 hover:text-red-300 transition"
            >
              Disconnect
            </button>
          </>
        ) : (
          <button
            onClick={handleConnect}
            className="w-full px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition"
          >
            Sign In to Swap
          </button>
        )}
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-900/30 border-b border-red-700/50 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Swap widget with error boundary */}
      <div className="p-4">
        <WidgetErrorBoundary fallback={widgetFallback}>
          <WidgetConfigProvider config={widgetConfig as WidgetConfig} theme={theme}>
            <Widget />
          </WidgetConfigProvider>
        </WidgetErrorBoundary>
      </div>

      {/* Info footer */}
      <div className="px-4 py-3 border-t border-slate-700 bg-slate-900/50">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>3% swap fee to vitalpointai.near</span>
          <a 
            href="https://docs.intents.aurora.dev/" 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Powered by NEAR Intents
          </a>
        </div>
      </div>
    </div>
  );
}
