import { AlertCircle, FileText, Upload } from 'lucide-react';
import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';

interface TickDataDropZoneProps {
  onFileAccepted: (file: File) => void;
  isLoading: boolean;
  error?: string | null;
  loadingLabel?: string;
  isIndeterminate?: boolean;
  uploadProgress?: {
    loadedBytes: number;
    totalBytes: number | null;
    percent: number | null;
  } | null;
}

function formatUploadBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  }

  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** Drag-and-drop upload zone for NinjaTrader tick-data text files. */
export function TickDataDropZone({
  onFileAccepted,
  isLoading,
  error,
  loadingLabel,
  isIndeterminate,
  uploadProgress,
}: TickDataDropZoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const nextFile = acceptedFiles[0];
      if (nextFile) {
        onFileAccepted(nextFile);
      }
    },
    [onFileAccepted]
  );

  const { getRootProps, getInputProps, isDragActive, acceptedFiles } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.txt'],
      'application/octet-stream': ['.txt'],
    },
    maxFiles: 1,
    disabled: isLoading,
  });

  const selectedFile = acceptedFiles[0];

  return (
    <div className="w-full">
      <div
        {...getRootProps()}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
          isDragActive
            ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20'
            : 'border-gray-300 hover:border-brand-400 hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-800'
        } ${isLoading ? 'cursor-not-allowed opacity-50' : ''}`}
      >
        <input {...getInputProps()} aria-label="Upload NinjaTrader tick-data file" />
        <div className="flex flex-col items-center gap-3">
          {isLoading ? (
            uploadProgress ? (
              <div className="w-full max-w-sm space-y-3">
                <div className="flex items-center justify-center gap-2">
                  <FileText className="h-8 w-8 text-brand-600" />
                  <div className="text-left">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {loadingLabel ?? 'Uploading tick data...'}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {isIndeterminate
                        ? 'Server-side parsing in progress'
                        : uploadProgress.percent !== null
                        ? `${uploadProgress.percent.toFixed(1)}%`
                        : 'Uploading...'}
                    </p>
                  </div>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  {isIndeterminate ? (
                    <div className="relative h-full w-full overflow-hidden">
                      <div className="absolute inset-y-0 left-0 w-full rounded-full bg-brand-200/70 dark:bg-brand-900/40" />
                      <div className="absolute inset-y-0 left-0 w-full rounded-full bg-brand-600 animate-pulse" />
                    </div>
                  ) : (
                    <div
                      className="h-full rounded-full bg-brand-600 transition-all"
                      style={{
                        width: `${Math.min(
                          Math.max(uploadProgress.percent ?? 0, 2),
                          100
                        )}%`,
                      }}
                    />
                  )}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {isIndeterminate ? (
                    <>
                      Uploaded {formatUploadBytes(uploadProgress.loadedBytes)}
                      {uploadProgress.totalBytes !== null
                        ? ` of ${formatUploadBytes(uploadProgress.totalBytes)}`
                        : ''}
                    </>
                  ) : (
                    <>
                      {formatUploadBytes(uploadProgress.loadedBytes)}
                      {uploadProgress.totalBytes !== null
                        ? ` / ${formatUploadBytes(uploadProgress.totalBytes)}`
                        : ''}
                    </>
                  )}
                </p>
              </div>
            ) : (
              <>
                <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-brand-600" />
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {loadingLabel ?? 'Uploading and previewing tick data...'}
                </p>
              </>
            )
          ) : selectedFile ? (
            <>
              <FileText className="h-10 w-10 text-brand-600" />
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {selectedFile.name}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {Math.max(selectedFile.size / 1024 / 1024, 0.01).toFixed(2)} MB
              </p>
            </>
          ) : (
            <>
              <Upload className="h-10 w-10 text-gray-400 dark:text-gray-500" />
              {isDragActive ? (
                <p className="text-sm font-medium text-brand-600">
                  Drop the NinjaTrader .txt file here...
                </p>
              ) : (
                <>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    <span className="font-medium text-brand-600">Click to upload</span> or drag and drop
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    One NinjaTrader tick-data .txt export
                  </p>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {error ? (
        <div className="mt-3 flex items-center gap-2 rounded-md bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}
    </div>
  );
}
