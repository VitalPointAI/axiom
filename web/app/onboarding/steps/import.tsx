'use client';

import { useState, useRef, useCallback } from 'react';
import { Upload, CheckCircle, XCircle, ChevronRight, FileSpreadsheet } from 'lucide-react';

interface ImportStepProps {
  onNext: () => void;
  onSkip: () => void;
}

interface UploadedFile {
  id: string;
  name: string;
  status: 'uploading' | 'success' | 'error';
  error?: string;
}

const SUPPORTED_EXCHANGES = [
  { name: 'Coinbase', emoji: '🔵' },
  { name: 'Crypto.com', emoji: '🔷' },
  { name: 'Wealthsimple', emoji: '🟢' },
  { name: 'Uphold', emoji: '⬆️' },
  { name: 'Coinsquare', emoji: '🟡' },
];

export function ImportStep({ onNext, onSkip }: ImportStepProps) {
  const [dragActive, setDragActive] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadFile = useCallback(async (file: File) => {
    const id = Math.random().toString(36).substring(2, 9);
    setUploadedFiles((prev) => [...prev, { id, name: file.name, status: 'uploading' }]);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/upload-file', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });

      if (res.ok) {
        setUploadedFiles((prev) =>
          prev.map((f) => (f.id === id ? { ...f, status: 'success' } : f))
        );
      } else {
        const data = await res.json().catch(() => ({}));
        setUploadedFiles((prev) =>
          prev.map((f) =>
            f.id === id
              ? { ...f, status: 'error', error: String((data as Record<string, unknown>)?.detail || 'Upload failed') }
              : f
          )
        );
      }
    } catch {
      setUploadedFiles((prev) =>
        prev.map((f) => (f.id === id ? { ...f, status: 'error', error: 'Network error' } : f))
      );
    }
  }, []);

  const handleFilesSelected = useCallback(
    (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      fileArray.forEach((file) => uploadFile(file));
    },
    [uploadFile]
  );

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

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 space-y-5">
      <div>
        <h2 className="text-xl font-bold text-white">Import Exchange Data</h2>
        <p className="text-gray-400 text-sm mt-1">
          Upload transaction history files from your exchanges. This step is optional — you can
          import files later from the dashboard.
        </p>
      </div>

      {/* Supported exchanges */}
      <div className="flex flex-wrap gap-2">
        {SUPPORTED_EXCHANGES.map((exchange) => (
          <span
            key={exchange.name}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 border border-gray-700 rounded-full text-xs text-gray-300"
          >
            <span>{exchange.emoji}</span>
            {exchange.name}
          </span>
        ))}
      </div>

      {/* Drop zone */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          dragActive
            ? 'border-blue-500 bg-blue-900/20'
            : 'border-gray-600 hover:border-blue-500 hover:bg-gray-900/50'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".csv,.xlsx,.xls,.pdf"
          onChange={(e) => e.target.files && handleFilesSelected(e.target.files)}
          className="hidden"
        />
        <Upload className={`w-10 h-10 mx-auto mb-3 ${dragActive ? 'text-blue-400' : 'text-gray-500'}`} />
        <p className="text-white font-medium">Drop your exchange CSV files here</p>
        <p className="text-gray-500 text-sm mt-1">or click to browse — CSV, XLSX, PDF supported</p>
      </div>

      {/* Uploaded files */}
      {uploadedFiles.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-300">Uploaded Files</h3>
          <div className="space-y-2">
            {uploadedFiles.map((file) => (
              <div
                key={file.id}
                className={`flex items-center gap-3 p-3 rounded-lg border ${
                  file.status === 'success'
                    ? 'bg-green-900/20 border-green-700'
                    : file.status === 'error'
                    ? 'bg-red-900/20 border-red-700'
                    : 'bg-gray-900 border-gray-700'
                }`}
              >
                {file.status === 'uploading' && (
                  <FileSpreadsheet className="w-4 h-4 text-blue-400 animate-pulse flex-shrink-0" />
                )}
                {file.status === 'success' && (
                  <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
                )}
                {file.status === 'error' && (
                  <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{file.name}</p>
                  {file.status === 'uploading' && (
                    <p className="text-xs text-blue-400">Uploading...</p>
                  )}
                  {file.status === 'success' && (
                    <p className="text-xs text-green-400">Uploaded successfully</p>
                  )}
                  {file.status === 'error' && (
                    <p className="text-xs text-red-400">{file.error || 'Upload failed'}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="space-y-2 pt-2">
        <button
          onClick={onNext}
          className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition-colors"
        >
          Continue
          <ChevronRight className="w-4 h-4" />
        </button>
        <button
          onClick={onNext}
          className="w-full text-sm text-gray-400 hover:text-gray-300 transition-colors py-2"
        >
          Skip this step
          <ChevronRight className="w-3 h-3 inline ml-1" />
        </button>
        <button
          onClick={onSkip}
          className="w-full text-xs text-gray-600 hover:text-gray-500 transition-colors py-1"
        >
          Skip to dashboard
        </button>
      </div>
    </div>
  );
}
