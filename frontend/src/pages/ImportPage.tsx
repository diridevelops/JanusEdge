import { Check, ChevronLeft, ChevronRight, Upload } from 'lucide-react';
import { FeeEntryTable } from '../components/import/FeeEntryTable';
import { FileDropZone } from '../components/import/FileDropZone';
import { ImportPreview } from '../components/import/ImportPreview';
import { ImportSummary } from '../components/import/ImportSummary';
import { ValidationErrors } from '../components/import/ValidationErrors';
import type { ImportStep } from '../hooks/useImport';
import { useImport } from '../hooks/useImport';

const STEP_LABELS: Record<ImportStep, string> = {
  upload: 'Upload CSV',
  preview: 'Preview Executions',
  fees: 'Assign Fees',
  summary: 'Summary',
};

const STEPS: ImportStep[] = ['upload', 'preview', 'fees', 'summary'];

/** CSV Import wizard page with multi-step flow. */
export function ImportPage() {
  const wizard = useImport();

  const currentStepIndex = STEPS.indexOf(wizard.step);

  function handleFileAccepted(files: File[]) {
    wizard.handleUpload(files);
  }

  async function handleConfirmPreview() {
    await wizard.handleReconstruct();
  }

  async function handleConfirmFees() {
    await wizard.handleFinalize();
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Import Trades</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload one or more CSV exports from NinjaTrader or Quantower to import your trades.
        </p>
      </div>

      {/* Step indicator */}
      {wizard.step !== 'summary' && (
        <nav aria-label="Import progress">
          <ol className="flex items-center">
            {STEPS.filter((s) => s !== 'summary').map((step, idx) => {
              const isCurrent = step === wizard.step;
              const isCompleted = idx < currentStepIndex;
              return (
                <li
                  key={step}
                  className={`flex items-center ${idx < 2 ? 'flex-1' : ''}`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium
                        ${
                          isCompleted
                            ? 'bg-brand-600 text-white'
                            : isCurrent
                              ? 'bg-brand-100 text-brand-700 ring-2 ring-brand-600'
                              : 'bg-gray-100 text-gray-500'
                        }`}
                    >
                      {isCompleted ? (
                        <Check className="h-4 w-4" />
                      ) : (
                        idx + 1
                      )}
                    </span>
                    <span
                      className={`text-sm font-medium ${
                        isCurrent ? 'text-brand-700' : 'text-gray-500'
                      }`}
                    >
                      {STEP_LABELS[step]}
                    </span>
                  </div>
                  {idx < 2 && (
                    <div
                      className={`flex-1 h-0.5 mx-4 ${
                        isCompleted ? 'bg-brand-600' : 'bg-gray-200'
                      }`}
                    />
                  )}
                </li>
              );
            })}
          </ol>
        </nav>
      )}

      {/* Step content */}
      <div className="card p-6">
        {/* Step 1: Upload */}
        {wizard.step === 'upload' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Upload CSV Files
            </h2>
            <FileDropZone
              onFileAccepted={handleFileAccepted}
              isLoading={wizard.isLoading}
              error={wizard.error}
            />
          </div>
        )}

        {/* Step 2: Preview */}
        {wizard.step === 'preview' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Preview Parsed Executions
            </h2>

            {wizard.parseErrors.length > 0 && (
              <ValidationErrors errors={wizard.parseErrors} />
            )}

            {wizard.warnings.length > 0 && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
                {wizard.warnings.map((w, i) => (
                  <p key={i}>{w}</p>
                ))}
              </div>
            )}

            <ImportPreview
              executions={wizard.executions}
              platform={wizard.platform}
              fileName={wizard.fileName}
              totalRows={wizard.totalRows}
              parsedRows={wizard.parsedRows}
            />

            {wizard.error && (
              <div className="text-sm text-red-600 bg-red-50 p-3 rounded-md">
                {wizard.error}
              </div>
            )}

            <div className="flex justify-between pt-4">
              <button
                onClick={() => wizard.goToStep('upload')}
                className="btn-secondary inline-flex items-center gap-1.5"
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </button>
              <button
                onClick={handleConfirmPreview}
                disabled={wizard.isLoading || wizard.executions.length === 0}
                className="btn-primary inline-flex items-center gap-1.5"
              >
                {wizard.isLoading ? (
                  'Reconstructing...'
                ) : (
                  <>
                    Reconstruct Trades
                    <ChevronRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Fee Entry */}
        {wizard.step === 'fees' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Assign Fees to Trades
            </h2>
            <p className="text-sm text-gray-500">
              {wizard.trades.length} {wizard.trades.length === 1 ? 'trade' : 'trades'}{' '}
              reconstructed. Enter commission/fees for each trade or use bulk entry.
            </p>

            <FeeEntryTable
              trades={wizard.trades}
              fees={wizard.fees}
              onFeeChange={wizard.setFee}
              onBulkFee={wizard.setBulkFee}
            />

            {wizard.error && (
              <div className="text-sm text-red-600 bg-red-50 p-3 rounded-md">
                {wizard.error}
              </div>
            )}

            <div className="flex justify-between pt-4">
              <button
                onClick={() => wizard.goToStep('preview')}
                className="btn-secondary inline-flex items-center gap-1.5"
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </button>
              <button
                onClick={handleConfirmFees}
                disabled={wizard.isLoading}
                className="btn-primary inline-flex items-center gap-1.5"
              >
                {wizard.isLoading ? (
                  'Finalizing...'
                ) : (
                  <>
                    <Upload className="h-4 w-4" />
                    Finalize Import
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Summary */}
        {wizard.step === 'summary' && (
          <ImportSummary
            tradeCount={wizard.finalizedCount}
            platform={wizard.platform}
            fileName={wizard.fileName}
            trades={wizard.trades}
            fees={wizard.fees}
            onImportAnother={wizard.reset}
          />
        )}
      </div>
    </div>
  );
}
