import { apiBaseUrl } from '@/config/env';
import type { HealthResponse } from '@/interfaces/health.interface';

/** GET /health; throws on any non-2xx so the query shows the error state. */
export const getHealth = async (): Promise<HealthResponse> => {
  const response = await fetch(`${apiBaseUrl()}/health`);
  if (!response.ok) throw new Error(`Health check failed with ${String(response.status)}`);
  return (await response.json()) as HealthResponse;
};
