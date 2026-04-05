import { AlertCircle, FileText, Upload } from 'lucide-react';
import { useCallback } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import type { UploadRuleConfig } from '../../types/clientConfig.types';

interface FileDropZoneProps {
  /** Called when one or more valid CSV files are accepted. */
  onFileAccepted: (files: File[]) => void;
  /** Called when one or more selected files are rejected client-side. */
  onFileRejected?: (message: string) => void;
  /** Whether submission is in progress. */
  isLoading: boolean;
  /** Error message to display. */
  error?: string | null;
  /** Backend-driven upload rules when available. */
  uploadRule?: UploadRuleConfig | null;
}

function getDropzoneErrorMessage(
  rejections: FileRejection[],
  uploadRule?: UploadRuleConfig | null
): string {
  const firstError = rejections[0]?.errors[0];

  switch (firstError?.code) {
    case 'file-too-large':
      return uploadRule
        ? `CSV files must be ${uploadRule.max_size_label} or smaller.`
        : 'One or more selected files exceed the server upload limit.';
    case 'file-invalid-type':
      return uploadRule
        ? 'Only .csv files are supported.'
        : 'Unable to upload that file. Please choose a valid CSV export.';
    default:
      return uploadRule
        ? 'Unable to upload one or more selected files. Please review the CSV export and try again.'
        : 'Unable to upload one or more selected files. The server will validate them after upload.';
  }
}

function buildDropzoneAccept(
  uploadRule?: UploadRuleConfig | null
): Record<string, string[]> | undefined {
  if (
    !uploadRule
    || uploadRule.accepted_mime_types.length === 0
    || uploadRule.accepted_extensions.length === 0
  ) {
    return undefined;
  }

  return Object.fromEntries(
    uploadRule.accepted_mime_types.map((mimeType) => [
      mimeType,
      uploadRule.accepted_extensions,
    ])
  );
}

/** Drag-and-drop file upload zone for CSV files. */
export function FileDropZone({
  onFileAccepted,
  onFileRejected,
  isLoading,
  error,
  uploadRule,
}: FileDropZoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[], fileRejections: FileRejection[]) => {
      if (fileRejections.length > 0) {
        onFileRejected?.(
          getDropzoneErrorMessage(fileRejections, uploadRule)
        );
        return;
      }

      if (acceptedFiles.length > 0) {
        onFileAccepted(acceptedFiles);
      }
    },
    [onFileAccepted, onFileRejected, uploadRule]
  );

  const { getRootProps, getInputProps, isDragActive, acceptedFiles } =
    useDropzone({
      onDrop,
      accept: buildDropzoneAccept(uploadRule),
      maxSize: uploadRule?.max_size_bytes,
      disabled: isLoading,
    });

  const selectedFiles = acceptedFiles;

  return (
    <div className="w-full">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors
          ${isDragActive ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-gray-300 dark:border-gray-600 hover:border-brand-400 hover:bg-gray-50 dark:hover:bg-gray-800'}
          ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}
        `}
      >
        <input {...getInputProps()} aria-label="Upload CSV file" />
        <div className="flex flex-col items-center gap-3">
          {isLoading ? (
            <>
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600" />
              <p className="text-sm text-gray-600 dark:text-gray-400">Uploading and parsing file...</p>
            </>
          ) : selectedFiles.length > 0 ? (
            <>
              <FileText className="h-10 w-10 text-brand-600" />
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {selectedFiles.length} file{selectedFiles.length === 1 ? '' : 's'} selected
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
                {selectedFiles.slice(0, 3).map((file) => file.name).join(', ')}
                {selectedFiles.length > 3 ? '...' : ''}
              </p>
            </>
          ) : (
            <>
              <Upload className="h-10 w-10 text-gray-400 dark:text-gray-500" />
              {isDragActive ? (
                <p className="text-sm text-brand-600 font-medium">Drop CSV files here...</p>
              ) : (
                <>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    <span className="font-medium text-brand-600">Click to upload</span> or drag
                    and drop
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {uploadRule
                      ? `One or more CSV files (NinjaTrader, Quantower) - Max ${uploadRule.max_size_label} each`
                      : 'One or more CSV files (NinjaTrader, Quantower)'}
                  </p>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-3 flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 p-3 rounded-md">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
