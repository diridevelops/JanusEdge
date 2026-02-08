import { AlertCircle, FileText, Upload } from 'lucide-react';
import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';

interface FileDropZoneProps {
  /** Called when a valid CSV file is accepted. */
  onFileAccepted: (file: File) => void;
  /** Whether submission is in progress. */
  isLoading: boolean;
  /** Error message to display. */
  error?: string | null;
}

/** Drag-and-drop file upload zone for CSV files. */
export function FileDropZone({
  onFileAccepted,
  isLoading,
  error,
}: FileDropZoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (file) {
        onFileAccepted(file);
      }
    },
    [onFileAccepted]
  );

  const { getRootProps, getInputProps, isDragActive, acceptedFiles } =
    useDropzone({
      onDrop,
      accept: { 'text/csv': ['.csv'] },
      maxFiles: 1,
      disabled: isLoading,
    });

  const selectedFile = acceptedFiles[0] ?? null;

  return (
    <div className="w-full">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors
          ${isDragActive ? 'border-brand-500 bg-brand-50' : 'border-gray-300 hover:border-brand-400 hover:bg-gray-50'}
          ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}
        `}
      >
        <input {...getInputProps()} aria-label="Upload CSV file" />
        <div className="flex flex-col items-center gap-3">
          {isLoading ? (
            <>
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600" />
              <p className="text-sm text-gray-600">Uploading and parsing file...</p>
            </>
          ) : selectedFile ? (
            <>
              <FileText className="h-10 w-10 text-brand-600" />
              <p className="text-sm font-medium text-gray-900">{selectedFile.name}</p>
              <p className="text-xs text-gray-500">
                {(selectedFile.size / 1024).toFixed(1)} KB
              </p>
            </>
          ) : (
            <>
              <Upload className="h-10 w-10 text-gray-400" />
              {isDragActive ? (
                <p className="text-sm text-brand-600 font-medium">Drop file here...</p>
              ) : (
                <>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium text-brand-600">Click to upload</span> or drag
                    and drop
                  </p>
                  <p className="text-xs text-gray-500">CSV files only (NinjaTrader, Quantower)</p>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-3 flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-md">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
