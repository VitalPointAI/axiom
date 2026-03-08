'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { 
  Upload, 
  FileSpreadsheet, 
  CheckCircle, 
  XCircle, 
  AlertTriangle,
  ArrowRight,
  ArrowLeft,
  RefreshCw,
  Trash2,
  ExternalLink,
  Check,
  AlertCircle,
  Info,
  Key,
  Eye,
  EyeOff,
  Link2,
  Plus,
  File
} from 'lucide-react';

// Exchange configurations
interface ExchangeConfig {
  id: string;
  name: string;
  logo: string;
  importMethod: 'csv' | 'api' | 'both';
  acceptedFormats: string;
  instructions: string[];
  instructionsUrl: string | null;
  apiFields?: { key: string; label: string; type: 'text' | 'password'; required: boolean }[];
  notes: string[];
}

const exchangeConfigs: Record<string, ExchangeConfig> = {
  'crypto.com': {
    id: 'crypto.com',
    name: 'Crypto.com App',
    logo: '🔷',
    importMethod: 'csv',
    acceptedFormats: '.csv',
    instructions: [
      'Open the Crypto.com App on your phone',
      'Go to Settings → Export',
      'Export "Crypto Wallet" as CSV',
      'Export "Fiat Wallet" as CSV (optional)',
      'Upload all exported files here',
    ],
    instructionsUrl: 'https://help.crypto.com/en/articles/3703222',
    notes: ['You can upload multiple transaction files at once'],
  },
  'coinbase': {
    id: 'coinbase',
    name: 'Coinbase',
    logo: '🔵',
    importMethod: 'csv',
    acceptedFormats: '.csv',
    instructions: [
      'Log in to Coinbase.com (web)',
      'Go to Reports → Transaction history',
      'Select date range (recommend "All time")',
      'Download CSV and upload here',
    ],
    instructionsUrl: 'https://help.coinbase.com/en/coinbase/taxes',
    notes: [],
  },
  'coinsquare': {
    id: 'coinsquare',
    name: 'Coinsquare',
    logo: '🟡',
    importMethod: 'csv',
    acceptedFormats: '.csv,.pdf,.xlsx,.xls',
    instructions: [
      'Log in to Coinsquare.com',
      'Go to Activity → Export',
      'Download any format statements',
    ],
    instructionsUrl: null,
    notes: ['Both CSV and PDF formats supported'],
  },
  'newton': {
    id: 'newton',
    name: 'Newton',
    logo: '🍎',
    importMethod: 'csv',
    acceptedFormats: '.csv',
    instructions: [
      'Log in to Newton',
      'Go to Settings → Export',
      'Download transaction history CSV',
    ],
    instructionsUrl: null,
    notes: [],
  },
  'shakepay': {
    id: 'shakepay',
    name: 'Shakepay',
    logo: '🟢',
    importMethod: 'csv',
    acceptedFormats: '.csv',
    instructions: [
      'Log in to Shakepay (web)',
      'Go to Settings → Tax Documents',
      'Download your transaction history',
    ],
    instructionsUrl: null,
    notes: [],
  },
  'kraken': {
    id: 'kraken',
    name: 'Kraken',
    logo: '🐙',
    importMethod: 'csv',
    acceptedFormats: '.csv',
    instructions: [
      'Log in to Kraken',
      'Go to History → Export',
      'Select "Ledgers" export type',
      'Download CSV and upload here',
    ],
    instructionsUrl: 'https://support.kraken.com/hc/en-us/articles/360001169383',
    notes: [],
  },
  'binance': {
    id: 'binance',
    name: 'Binance',
    logo: '🟨',
    importMethod: 'csv',
    acceptedFormats: '.csv',
    instructions: [
      'Log in to Binance',
      'Go to Orders → Transaction History',
      'Click Export → Generate statements',
      'Download and upload here',
    ],
    instructionsUrl: 'https://www.binance.com/en/support',
    notes: [],
  },
  'generic': {
    id: 'generic',
    name: 'Other Exchange',
    logo: '📄',
    importMethod: 'csv',
    acceptedFormats: '.csv',
    instructions: [
      'Export transaction history from your exchange',
      'Required columns: Date, Type, Asset, Amount',
      'Upload CSV file(s) here',
    ],
    instructionsUrl: null,
    notes: ['Generic format may need manual review'],
  },
};

interface UploadedFile {
  id: string;
  file: File;
  status: 'pending' | 'parsing' | 'done' | 'error' | 'merged';
  preview?: PreviewData;
  error?: string;
}

interface PreviewData {
  calculatedBalances?: Record<string, number>;
  exchange: string;
  totalRows: number;
  parsedCount: number;
  errorCount: number;
  preview: ParsedTransaction[];
  errors: string[];
}

interface ParsedTransaction {
  timestamp: string;
  txType: string;
  direction?: 'IN' | 'OUT' | 'INTERNAL';
  asset: string;
  amount: number;
  quoteAsset?: string;
  quoteAmount?: number;
  description?: string;
}

interface BalanceSummary {
  asset: string;
  calculated: number;
  verified?: number;
  status: 'ok' | 'warning' | 'error' | 'unverified';
}

type Step = 'select' | 'upload' | 'verify' | 'complete';

export default function ImportWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedExchange = searchParams.get('exchange');
  
  const [step, setStep] = useState<Step>(preselectedExchange ? 'upload' : 'select');
  const [selectedExchange, setSelectedExchange] = useState<string | null>(preselectedExchange);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [balances, setBalances] = useState<BalanceSummary[]>([]);
  const [verifiedBalances, setVerifiedBalances] = useState<Record<string, string>>({});
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [importResult, setImportResult] = useState<any>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const config = selectedExchange ? exchangeConfigs[selectedExchange] : null;

  // Generate unique ID
  const generateId = () => Math.random().toString(36).substring(2, 9);

  // Reset wizard
  const resetWizard = () => {
    setStep('select');
    setSelectedExchange(null);
    setUploadedFiles([]);
    setBalances([]);
    setVerifiedBalances({});
    setMessage(null);
    setImportResult(null);
  };

  // Handle exchange selection
  const handleSelectExchange = (exchangeId: string) => {
    setSelectedExchange(exchangeId);
    setUploadedFiles([]);
    setBalances([]);
    setStep('upload');
  };

  // Parse ALL files together (for proper deduplication)
  const parseAllFiles = async () => {
    const filesToParse = uploadedFiles.filter(f => f.status === 'pending' || f.status === 'done');
    if (filesToParse.length === 0) return;

    // Mark all as parsing
    setUploadedFiles(prev => prev.map(f => ({ ...f, status: 'parsing' as const })));

    try {
      const formData = new FormData();
      filesToParse.forEach((f, i) => {
        formData.append(`file_${i}`, f.file);
      });
      formData.append('preview', 'true');
      formData.append('exchange', selectedExchange || 'auto');

      const res = await fetch('/api/import/csv', {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();

      if (res.ok) {
        // Store the merged result on the first file, mark others as merged
        setUploadedFiles(prev => prev.map((f, i) => 
          i === 0 
            ? { ...f, status: 'done' as const, preview: data }
            : { ...f, status: 'merged' as const }
        ));
      } else {
        setUploadedFiles(prev => prev.map(f => 
          ({ ...f, status: 'error' as const, error: data.error || 'Parse failed' })
        ));
      }
    } catch (err) {
      setUploadedFiles(prev => prev.map(f => 
        ({ ...f, status: 'error' as const, error: 'Network error' })
      ));
    }
  };

  // Parse a single file
  const parseFile = async (uploadedFile: UploadedFile) => {
    setUploadedFiles(prev => prev.map(f => 
      f.id === uploadedFile.id ? { ...f, status: 'parsing' } : f
    ));

    try {
      const formData = new FormData();
      formData.append('file', uploadedFile.file);
      formData.append('preview', 'true');
      formData.append('exchange', selectedExchange || 'auto');

      const isPdf = uploadedFile.file.name.toLowerCase().endsWith('.pdf');
      const endpoint = isPdf ? '/api/import/pdf' : '/api/import/csv';

      const res = await fetch(endpoint, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();

      if (res.ok) {
        setUploadedFiles(prev => prev.map(f => 
          f.id === uploadedFile.id ? { ...f, status: 'done', preview: data } : f
        ));
      } else {
        setUploadedFiles(prev => prev.map(f => 
          f.id === uploadedFile.id ? { ...f, status: 'error', error: data.error || 'Parse failed' } : f
        ));
      }
    } catch (err) {
      setUploadedFiles(prev => prev.map(f => 
        f.id === uploadedFile.id ? { ...f, status: 'error', error: 'Upload failed' } : f
      ));
    }
  };

  // Handle file selection
  const handleFilesSelected = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    
    // Create uploaded file objects
    const newFiles: UploadedFile[] = fileArray.map(file => ({
      id: generateId(),
      file,
      status: 'pending' as const,
    }));

    // Add files to state first
    setUploadedFiles(prev => [...prev, ...newFiles]);

    // Then parse - always use batch parsing for proper deduplication
    // Small delay to ensure state is updated
    setTimeout(async () => {
      // Send ALL files to backend together
      const allFiles = [...uploadedFiles, ...newFiles];
      
      // Mark all as parsing
      setUploadedFiles(prev => prev.map(f => ({ ...f, status: 'parsing' as const })));

      try {
        const formData = new FormData();
        allFiles.forEach((f, i) => {
          formData.append(`file_${i}`, f.file);
        });
        formData.append('preview', 'true');
        formData.append('exchange', selectedExchange || 'auto');

        const res = await fetch('/api/import/csv', {
          method: 'POST',
          body: formData,
        });

        const data = await res.json();

        if (res.ok) {
          // Store result on first file, mark others as done
          setUploadedFiles(prev => prev.map((f, i) => ({
            ...f,
            status: 'done' as const,
            preview: i === 0 ? data : undefined
          })));
        } else {
          setUploadedFiles(prev => prev.map(f => ({
            ...f,
            status: 'error' as const,
            error: data.error || 'Parse failed'
          })));
        }
      } catch (err) {
        setUploadedFiles(prev => prev.map(f => ({
          ...f,
          status: 'error' as const,
          error: 'Network error'
        })));
      }
    }, 50);
  };

  // Handle drag events
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  };

  // Remove a file
  const removeFile = (id: string) => {
    setUploadedFiles(prev => prev.filter(f => f.id !== id));
  };

  // Calculate balances from server's pre-calculated balances
  const calculateBalances = useCallback(() => {
    // Merge calculatedBalances from all uploaded files
    const mergedBalances: Record<string, number> = {};

    for (const uploaded of uploadedFiles) {
      if (uploaded.status === 'merged') continue;
      if (uploaded.status !== 'done' || !uploaded.preview) continue;
      
      // Use the server's calculatedBalances directly
      const serverBalances = uploaded.preview.calculatedBalances || {};
      for (const [asset, amount] of Object.entries(serverBalances)) {
        if (!mergedBalances[asset]) {
          mergedBalances[asset] = 0;
        }
        mergedBalances[asset] += Number(amount) || 0;
      }
    }

    const summaries: BalanceSummary[] = Object.entries(mergedBalances)
      .map(([asset, calculated]) => ({
        asset,
        calculated,
        status: 'unverified' as const,
      }))
      .filter(b => Math.abs(b.calculated) > 0.0001)
      .sort((a, b) => Math.abs(b.calculated) - Math.abs(a.calculated));

    setBalances(summaries);
  }, [uploadedFiles]);

  useEffect(() => {
    if (step === 'verify') {
      calculateBalances();
    }
  }, [step, calculateBalances]);

  // Handle balance verification
  const handleVerifyBalance = (asset: string, value: string) => {
    setVerifiedBalances(prev => ({ ...prev, [asset]: value }));
    
    setBalances(prev => prev.map(b => {
      if (b.asset !== asset) return b;
      
      const verified = parseFloat(value);
      if (isNaN(verified)) {
        return { ...b, status: 'unverified', verified: undefined };
      }
      
      const diff = Math.abs(verified - b.calculated);
      const tolerance = Math.max(0.01, Math.abs(b.calculated) * 0.01);
      
      if (diff < tolerance) {
        return { ...b, status: 'ok', verified };
      } else if (b.calculated < 0) {
        return { ...b, status: 'error', verified };
      } else {
        return { ...b, status: 'warning', verified };
      }
    }));
  };

  // Import all files
  const handleImport = async () => {
    const filesToImport = uploadedFiles.filter(f => f.status === 'done');
    if (filesToImport.length === 0) return;

    setImporting(true);
    setMessage(null);

    try {
      const results = [];
      
      for (const uploaded of filesToImport) {
        const formData = new FormData();
        formData.append('file', uploaded.file);
        formData.append('exchange', selectedExchange || 'auto');

        const isPdf = uploaded.file.name.toLowerCase().endsWith('.pdf');
        const endpoint = isPdf ? '/api/import/pdf' : '/api/import/csv';

        const res = await fetch(endpoint, {
          method: 'POST',
          body: formData,
        });

        const data = await res.json();
        results.push({ file: uploaded.file.name, ...data });
      }

      // Create adjustment transactions for discrepancies
      const adjustments = balances
        .filter(b => b.status === 'warning' && b.verified !== undefined)
        .map(b => ({
          asset: b.asset,
          calculated: b.calculated,
          actual: b.verified!,
          adjustment: b.verified! - b.calculated,
        }));

      if (adjustments.length > 0) {
        await fetch('/api/import/adjustments', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ exchange: selectedExchange, adjustments }),
        });
      }

      const totalImported = results.reduce((sum, r) => sum + (r.imported || 0), 0);
      const totalSkipped = results.reduce((sum, r) => sum + (r.skipped || 0), 0);

      setImportResult({ results, adjustments, totalImported, totalSkipped });
      setMessage({ 
        type: 'success', 
        text: `Imported ${totalImported} transactions from ${results.length} file(s)` 
      });
      setStep('complete');

    } catch (err) {
      setMessage({ type: 'error', text: 'Import failed. Please try again.' });
    } finally {
      setImporting(false);
    }
  };

  // Get total parsed count
  const totalParsed = uploadedFiles
    .filter(f => f.status === 'done')
    .reduce((sum, f) => sum + (f.preview?.parsedCount || 0), 0);

  const hasFiles = uploadedFiles.length > 0;
  const allFilesDone = uploadedFiles.every(f => f.status === 'done' || f.status === 'error');
  const hasValidFiles = uploadedFiles.some(f => f.status === 'done');

  // Render step content
  const renderStep = () => {
    switch (step) {
      case 'select':
        return (
          <div className="space-y-6">
            <div className="text-center">
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Select Your Exchange</h2>
              <p className="text-slate-500 mt-1">Choose where to import transactions from</p>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {Object.values(exchangeConfigs).map((exchange) => (
                <button
                  key={exchange.id}
                  onClick={() => handleSelectExchange(exchange.id)}
                  className="p-4 border-2 rounded-xl text-center transition hover:border-blue-400 hover:bg-blue-50 border-slate-200"
                >
                  <span className="text-3xl">{exchange.logo}</span>
                  <p className="mt-2 font-medium text-slate-900 text-sm">{exchange.name}</p>
                </button>
              ))}
            </div>
          </div>
        );

      case 'upload':
        if (!config) return null;
        return (
          <div className="space-y-5">
            <div className="text-center">
              <span className="text-3xl">{config.logo}</span>
              <h2 className="text-xl font-semibold text-slate-900 mt-2">Import from {config.name}</h2>
            </div>

            {/* Instructions */}
            <div className="bg-blue-50 rounded-xl p-4">
              <h3 className="font-medium text-blue-900 text-sm mb-2">Export Instructions:</h3>
              <ol className="space-y-1">
                {config.instructions.map((instruction, i) => (
                  <li key={i} className="flex items-start gap-2 text-blue-800 text-sm">
                    <span className="flex-shrink-0 w-5 h-5 bg-blue-200 rounded-full flex items-center justify-center text-xs font-medium">
                      {i + 1}
                    </span>
                    <span>{instruction}</span>
                  </li>
                ))}
              </ol>
              {config.instructionsUrl && (
                <a 
                  href={config.instructionsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-blue-600 hover:underline text-xs"
                >
                  Official guide <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>

            {/* Drop Zone */}
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition ${
                dragActive 
                  ? 'border-blue-500 bg-blue-50' 
                  : 'border-slate-300 hover:border-blue-400 hover:bg-blue-50/50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={config.acceptedFormats}
                onChange={(e) => e.target.files && handleFilesSelected(e.target.files)}
                className="hidden"
              />
              <Upload className={`w-10 h-10 mx-auto ${dragActive ? 'text-blue-500' : 'text-slate-400'}`} />
              <p className="mt-2 font-medium text-slate-700">
                Drop files here or click to browse
              </p>
              <p className="text-sm text-slate-500 mt-1">
                Drop your export files here • {config.acceptedFormats.replace(/\./g, '').toUpperCase()}
              </p>
            </div>

            {/* File List */}
            {hasFiles && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-slate-700">
                  Uploaded Files ({uploadedFiles.length})
                </h4>
                <div className="space-y-2">
                  {uploadedFiles.map((uploaded) => (
                    <div 
                      key={uploaded.id}
                      className={`flex items-center justify-between p-3 rounded-lg border ${
                        uploaded.status === 'done' ? 'bg-green-50 border-green-200' :
                        uploaded.status === 'error' ? 'bg-red-50 border-red-200' :
                        uploaded.status === 'parsing' ? 'bg-blue-50 border-blue-200' :
                        'bg-slate-50 border-slate-200'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        {uploaded.status === 'parsing' && (
                          <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />
                        )}
                        {uploaded.status === 'done' && (
                          <CheckCircle className="w-4 h-4 text-green-500" />
                        )}
                        {uploaded.status === 'error' && (
                          <XCircle className="w-4 h-4 text-red-500" />
                        )}
                        {uploaded.status === 'pending' && (
                          <File className="w-4 h-4 text-slate-400" />
                        )}
                        <div>
                          <p className="text-sm font-medium text-slate-700">
                            {uploaded.file.name}
                          </p>
                          {uploaded.status === 'done' && uploaded.preview && (
                            <p className="text-xs text-green-600">
                              {uploaded.preview.parsedCount} transactions parsed
                            </p>
                          )}
                          {uploaded.status === 'error' && (
                            <p className="text-xs text-red-600">{uploaded.error}</p>
                          )}
                          {uploaded.status === 'parsing' && (
                            <p className="text-xs text-blue-600">Parsing...</p>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); removeFile(uploaded.id); }}
                        className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>

                {allFilesDone && hasValidFiles && (
                  <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                    <span className="text-sm text-slate-600">
                      Total: <strong>{totalParsed.toLocaleString()}</strong> transactions
                    </span>
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700"
                    >
                      <Plus className="w-4 h-4" />
                      Add more files
                    </button>
                  </div>
                )}
              </div>
            )}

            {config.notes.length > 0 && (
              <div className="text-xs text-slate-500">
                {config.notes.map((note, i) => (
                  <p key={i}>💡 {note}</p>
                ))}
              </div>
            )}
          </div>
        );

      case 'verify':
        return (
          <div className="space-y-5">
            <div className="text-center">
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Verify Balances</h2>
              <p className="text-slate-500 text-sm">
                Optional: Enter actual balances to verify accuracy
              </p>
            </div>

            <div className="bg-white rounded-xl border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b">
                  <tr>
                    <th className="text-left px-4 py-2">Asset</th>
                    <th className="text-right px-4 py-2">Calculated</th>
                    <th className="text-center px-4 py-2">Actual</th>
                    <th className="w-12"></th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {balances.slice(0, 20).map((balance) => (
                    <tr key={balance.asset} className={balance.calculated < 0 ? 'bg-red-50' : ''}>
                      <td className="px-4 py-2 font-medium">{balance.asset}</td>
                      <td className={`px-4 py-2 text-right font-mono text-xs ${
                        balance.calculated < 0 ? 'text-red-600' : ''
                      }`}>
                        {balance.calculated.toLocaleString(undefined, { maximumFractionDigits: 4 })}
                      </td>
                      <td className="px-4 py-2">
                        <input
                          type="number"
                          step="any"
                          placeholder="—"
                          value={verifiedBalances[balance.asset] || ''}
                          onChange={(e) => handleVerifyBalance(balance.asset, e.target.value)}
                          className="w-full px-2 py-1 border rounded text-right font-mono text-xs"
                        />
                      </td>
                      <td className="px-2 text-center">
                        {balance.status === 'ok' && <CheckCircle className="w-4 h-4 text-green-500" />}
                        {balance.status === 'warning' && <AlertTriangle className="w-4 h-4 text-amber-500" />}
                        {balance.status === 'error' && <XCircle className="w-4 h-4 text-red-500" />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {balances.length > 20 && (
                <div className="p-2 text-center text-xs text-slate-500 border-t">
                  + {balances.length - 20} more
                </div>
              )}
            </div>

            <p className="text-xs text-slate-500 text-center">
              Mismatches will create adjustment transactions. Leave blank to skip verification.
            </p>
          </div>
        );

      case 'complete':
        return (
          <div className="space-y-6 text-center py-6">
            <CheckCircle className="w-16 h-16 text-green-500 mx-auto" />
            <div>
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Import Complete!</h2>
              <p className="text-slate-500 mt-1">
                {importResult?.totalImported || 0} transactions imported
                {importResult?.totalSkipped > 0 && ` (${importResult.totalSkipped} duplicates skipped)`}
              </p>
            </div>

            <div className="flex justify-center gap-3 pt-4">
              <button
                onClick={resetWizard}
                className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
              >
                Import More
              </button>
              <button
                onClick={() => router.push('/dashboard/transactions')}
                className="px-5 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 text-sm"
              >
                View Transactions
              </button>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="max-w-2xl mx-auto py-8 px-4 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Import Transactions</h1>
        <p className="text-slate-500 mt-1">Import from exchanges via transaction files</p>
      </div>

      {/* Message */}
      {message && (
        <div className={`p-3 rounded-lg flex items-center gap-2 text-sm ${
          message.type === 'success' 
            ? 'bg-green-50 text-green-800 border border-green-200'
            : message.type === 'info'
            ? 'bg-blue-50 text-blue-800 border border-blue-200'
            : 'bg-red-50 text-red-800 border border-red-200'
        }`}>
          {message.type === 'success' ? <CheckCircle className="w-4 h-4" /> : 
           message.type === 'info' ? <Info className="w-4 h-4" /> : 
           <XCircle className="w-4 h-4" />}
          {message.text}
        </div>
      )}

      {/* Progress */}
      {step !== 'complete' && (
        <div className="flex items-center justify-center gap-1">
          {['select', 'upload', 'verify'].map((s, i) => {
            const stepOrder = ['select', 'upload', 'verify'];
            const currentIdx = stepOrder.indexOf(step);
            const thisIdx = stepOrder.indexOf(s);
            return (
              <div key={s} className="flex items-center">
                <div className={`w-2 h-2 rounded-full ${
                  currentIdx >= thisIdx ? 'bg-blue-500' : 'bg-slate-200'
                }`} />
                {i < 2 && <div className={`w-8 h-0.5 ${
                  currentIdx > thisIdx ? 'bg-blue-500' : 'bg-slate-200'
                }`} />}
              </div>
            );
          })}
        </div>
      )}

      {/* Content */}
      <div className="bg-white rounded-xl border p-6">
        {renderStep()}
      </div>

      {/* Navigation */}
      {step !== 'select' && step !== 'complete' && (
        <div className="flex justify-between">
          <button
            onClick={() => {
              if (step === 'upload') {
                setStep('select');
                setSelectedExchange(null);
                setUploadedFiles([]);
              } else if (step === 'verify') {
                setStep('upload');
              }
            }}
            className="px-4 py-2 text-slate-600 hover:text-slate-900 flex items-center gap-2 text-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>

          {step === 'upload' && (
            <button
              onClick={() => setStep('verify')}
              disabled={!hasValidFiles || !allFilesDone}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 text-sm"
            >
              Preview & Verify
              <ArrowRight className="w-4 h-4" />
            </button>
          )}

          {step === 'verify' && (
            <button
              onClick={handleImport}
              disabled={importing}
              className="px-5 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center gap-2 text-sm"
            >
              {importing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              {importing ? 'Importing...' : `Import ${totalParsed} Transactions`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
