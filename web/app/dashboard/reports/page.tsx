'use client';

import { useState, useEffect, useRef } from 'react';
import { apiClient, API_URL, ApiError } from '@/lib/api';
import {
  FileText,
  Download,
  TrendingUp,
  DollarSign,
  RefreshCw,
  Globe,
  BookOpen,
  Coins,
  AlertTriangle,
  CheckCircle,
  Loader2,
} from 'lucide-react';

// FastAPI preview types
type PreviewType = 'capital-gains' | 'income' | 'ledger' | 't1135' | 'superficial-losses' | 'holdings';

interface PreviewRow {
  [key: string]: string | number | boolean | null;
}

interface PreviewResponse {
  type: PreviewType;
  rows: PreviewRow[];
  total: number;
}

interface GenerateResponse {
  job_id: string;
}

interface JobStatusResponse {
  status: string;
  progress_fetched: number;
  progress_total: number;
}

interface DownloadFile {
  filename: string;
  size: number;
  url: string;
}

interface DownloadListResponse {
  files: DownloadFile[];
}

interface ReportStatusResponse {
  exists: boolean;
  year: number;
  files?: string[];
}

type ReportTab = 'capital-gains' | 'income' | 'ledger' | 't1135' | 'superficial-losses' | 'holdings' | 'generate';

interface TabConfig {
  id: ReportTab;
  label: string;
  icon: typeof FileText;
  description: string;
  previewType?: PreviewType;
}

const tabs: TabConfig[] = [
  { id: 'capital-gains', label: 'Capital Gains', icon: TrendingUp, description: 'Gains & losses', previewType: 'capital-gains' },
  { id: 'income', label: 'Income', icon: DollarSign, description: 'All income sources', previewType: 'income' },
  { id: 'ledger', label: 'Ledger', icon: BookOpen, description: 'Transaction ledger', previewType: 'ledger' },
  { id: 't1135', label: 'T1135', icon: Globe, description: 'Foreign property', previewType: 't1135' },
  { id: 'superficial-losses', label: 'Superficial Losses', icon: AlertTriangle, description: 'Denied losses', previewType: 'superficial-losses' },
  { id: 'holdings', label: 'Holdings', icon: Coins, description: 'Portfolio holdings', previewType: 'holdings' },
  { id: 'generate', label: 'Generate Package', icon: FileText, description: 'Full tax package' },
];

export default function ReportsPage() {
  const [year, setYear] = useState(2025);
  const [activeTab, setActiveTab] = useState<ReportTab>('capital-gains');
  const [loading, setLoading] = useState(false);
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Generate package state
  const [taxTreatment, setTaxTreatment] = useState<'personal' | 'business'>('personal');
  const [generating, setGenerating] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [downloadFiles, setDownloadFiles] = useState<DownloadFile[]>([]);
  const [packageExists, setPackageExists] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load preview when tab or year changes
  useEffect(() => {
    const tab = tabs.find((t) => t.id === activeTab);
    if (tab?.previewType) {
      loadPreview(tab.previewType);
    } else if (activeTab === 'generate') {
      checkPackageStatus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, year]);

  const loadPreview = async (type: PreviewType) => {
    setLoading(true);
    setPreviewData(null);
    setPreviewError(null);
    try {
      const data = await apiClient.get<PreviewResponse>(`/api/reports/preview/${type}?year=${year}`);
      setPreviewData(data);
    } catch (err) {
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown>;
        setPreviewError(String(body?.detail || `Failed to load ${type} preview`));
      } else {
        setPreviewError(`Failed to load ${type} preview`);
      }
    } finally {
      setLoading(false);
    }
  };

  const checkPackageStatus = async () => {
    try {
      const status = await apiClient.get<ReportStatusResponse>(`/api/reports/status?year=${year}`);
      setPackageExists(status.exists);
      if (status.exists) {
        loadDownloadList();
      }
    } catch {
      setPackageExists(false);
    }
  };

  const loadDownloadList = async () => {
    try {
      const data = await apiClient.get<DownloadListResponse>(`/api/reports/download/${year}`);
      setDownloadFiles(data.files || []);
    } catch {
      setDownloadFiles([]);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setJobId(null);
    setJobStatus(null);
    try {
      const res = await apiClient.post<GenerateResponse>('/api/reports/generate', {
        year,
        tax_treatment: taxTreatment,
      });
      setJobId(res.job_id);
      startPolling(res.job_id);
    } catch (err) {
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown>;
        alert(`Generation failed: ${String(body?.detail || err.message)}`);
      } else {
        alert('Generation failed. Please try again.');
      }
      setGenerating(false);
    }
  };

  const startPolling = (id: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await apiClient.get<JobStatusResponse>(`/api/jobs/${id}/status`);
        setJobStatus(status);
        if (status.status === 'complete' || status.status === 'done') {
          if (pollRef.current) clearInterval(pollRef.current);
          setGenerating(false);
          setPackageExists(true);
          loadDownloadList();
        } else if (status.status === 'failed' || status.status === 'error') {
          if (pollRef.current) clearInterval(pollRef.current);
          setGenerating(false);
          alert('Report generation failed. Check that all transactions are classified.');
        }
      } catch {
        // ignore poll errors
      }
    }, 3000);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const downloadFile = (filename: string) => {
    window.open(`${API_URL}/api/reports/download/${year}/${encodeURIComponent(filename)}`, '_blank');
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const renderPreviewTable = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      );
    }

    if (previewError) {
      return (
        <div className="flex items-center gap-2 text-amber-600 p-6">
          <AlertTriangle className="w-5 h-5" />
          <span>{previewError}</span>
        </div>
      );
    }

    if (!previewData || previewData.rows.length === 0) {
      return (
        <div className="text-center text-slate-500 py-12">
          No data available for {year}. Generate the full package to populate these reports.
        </div>
      );
    }

    const columns = Object.keys(previewData.rows[0]);

    return (
      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm text-slate-500">
            Showing {previewData.rows.length} of {previewData.total} rows (preview)
          </p>
          {previewData.total > previewData.rows.length && (
            <p className="text-xs text-slate-400">Generate full package to access all rows</p>
          )}
        </div>
        <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/50 sticky top-0">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col}
                    className="text-left px-3 py-2 text-xs font-medium text-slate-500 uppercase whitespace-nowrap"
                  >
                    {col.replace(/_/g, ' ')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {previewData.rows.map((row, i) => (
                <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                  {columns.map((col) => (
                    <td key={col} className="px-3 py-2 text-slate-700 dark:text-slate-300 whitespace-nowrap">
                      {row[col] === null || row[col] === undefined
                        ? '-'
                        : typeof row[col] === 'number'
                        ? Number(row[col]).toLocaleString()
                        : String(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderGenerateTab = () => {
    const progressPct =
      jobStatus && jobStatus.progress_total > 0
        ? Math.round((jobStatus.progress_fetched / jobStatus.progress_total) * 100)
        : 0;

    return (
      <div className="space-y-6">
        {/* Config */}
        <div className="bg-slate-50 dark:bg-slate-900/30 rounded-lg p-6 space-y-4">
          <h3 className="font-medium text-slate-700 dark:text-slate-300">Generate Tax Package</h3>
          <p className="text-sm text-slate-500">
            Generates all report CSVs and PDFs for the selected year. All transactions must be
            classified before generating.
          </p>

          <div className="flex items-center gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                Tax Treatment
              </label>
              <select
                value={taxTreatment}
                onChange={(e) => setTaxTreatment(e.target.value as 'personal' | 'business')}
                className="px-3 py-2 border rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                disabled={generating}
              >
                <option value="personal">Personal (Capital Gains)</option>
                <option value="business">Business (Income)</option>
              </select>
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition font-medium"
          >
            {generating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FileText className="w-4 h-4" />
            )}
            {generating ? 'Generating...' : `Generate ${year} Package`}
          </button>
        </div>

        {/* Job progress */}
        {generating && jobStatus && (
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-sm text-blue-700 dark:text-blue-400">
              <span>Generating reports...</span>
              <span>{progressPct}%</span>
            </div>
            <div className="h-2 bg-blue-200 dark:bg-blue-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-600 transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <p className="text-xs text-blue-600 dark:text-blue-400">
              {jobStatus.progress_fetched} / {jobStatus.progress_total} steps
            </p>
          </div>
        )}

        {/* Download list */}
        {packageExists && downloadFiles.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
              <CheckCircle className="w-5 h-5" />
              <h3 className="font-medium">{year} Tax Package Ready</h3>
            </div>
            <div className="divide-y divide-slate-200 dark:divide-slate-700 border rounded-lg overflow-hidden">
              {downloadFiles.map((file) => (
                <div
                  key={file.filename}
                  className="flex items-center justify-between p-4 hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  <div>
                    <p className="font-medium text-slate-800 dark:text-slate-200 text-sm">
                      {file.filename}
                    </p>
                    <p className="text-xs text-slate-400">{formatSize(file.size)}</p>
                  </div>
                  <button
                    onClick={() => downloadFile(file.filename)}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition"
                  >
                    <Download className="w-4 h-4" />
                    Download
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {packageExists && downloadFiles.length === 0 && (
          <div className="text-slate-500 text-sm">
            Package generated — loading file list...
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Tax Reports</h1>
          <p className="text-slate-500 dark:text-slate-400">
            Canadian tax reporting suite — previews from live data
          </p>
        </div>
        <div className="flex items-center gap-4">
          <select
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
            className="border rounded-lg px-4 py-2 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
          >
            {[2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 overflow-x-auto">
        <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg min-w-max">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm whitespace-nowrap transition-colors ${
                  activeTab === tab.id
                    ? 'bg-white dark:bg-slate-700 text-blue-600 shadow-sm'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-white/50 dark:hover:bg-slate-700/50'
                }`}
                title={tab.description}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
        {activeTab === 'generate' ? renderGenerateTab() : renderPreviewTable()}
      </div>
    </div>
  );
}
