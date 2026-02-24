'use client';

import { useAuth } from "@/components/auth-provider";
import { SignInButton } from "@/components/sign-in-button";
import { redirect } from "next/navigation";
import { useEffect } from "react";

export default function Home() {
  const { user, isLoading } = useAuth();

  useEffect(() => {
    if (user && !isLoading) {
      redirect('/dashboard');
    }
  }, [user, isLoading]);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-slate-50 to-slate-100">
      <div className="max-w-md w-full mx-auto p-8">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-slate-900 mb-2">NearTax</h1>
          <p className="text-slate-600">
            Crypto tax reporting for Canadian businesses
          </p>
        </div>

        <div className="bg-white rounded-lg shadow-lg p-8">
          <div className="space-y-6">
            <div className="text-center">
              <h2 className="text-xl font-semibold text-slate-800 mb-2">
                Get Started
              </h2>
              <p className="text-sm text-slate-500 mb-6">
                Sign in with your NEAR wallet to manage your crypto tax reporting
              </p>
            </div>

            <SignInButton />

            <div className="text-center text-xs text-slate-400">
              <p>Supports NEAR, Ethereum, Polygon, and major exchanges</p>
            </div>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-3 gap-4 text-center text-sm text-slate-500">
          <div>
            <div className="text-2xl font-bold text-slate-700">64+</div>
            <div>Wallets</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-700">Multi</div>
            <div>Chain</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-700">CRA</div>
            <div>Ready</div>
          </div>
        </div>
      </div>
    </main>
  );
}
