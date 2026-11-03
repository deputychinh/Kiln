import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { HEALTH_QUERY_KEY } from '@/constants/query.constant';
import { getHealth } from '@/features/health/services/health.service';
import type { HealthResponse } from '@/interfaces/health.interface';

export const useApiHealth = (): UseQueryResult<HealthResponse> =>
  useQuery({ queryKey: HEALTH_QUERY_KEY, queryFn: getHealth, retry: false });
