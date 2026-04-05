/** Upload rule metadata returned by the backend client-config endpoint. */
export interface UploadRuleConfig {
  max_size_bytes: number;
  max_size_label: string;
  accepted_extensions: string[];
  accepted_mime_types: string[];
}

/** Public client config returned by the backend. */
export interface ClientConfig {
  uploads: {
    market_data: UploadRuleConfig;
    trade_import: UploadRuleConfig;
    media: UploadRuleConfig;
  };
}
