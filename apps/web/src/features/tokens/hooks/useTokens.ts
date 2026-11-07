import {
  useMutation,
  type UseMutationResult,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';

import { TOKENS_QUERY_KEY } from '@/constants/auth.constant';
import { createToken, listTokens, revokeToken } from '@/features/tokens/services/tokens.service';
import type { CreatedToken, CreateTokenRequest, TokenList } from '@/interfaces/auth.interface';

export const useTokens = (): UseQueryResult<TokenList> =>
  useQuery({ queryKey: TOKENS_QUERY_KEY, queryFn: ({ signal }) => listTokens(signal) });

/** Creates a token and refreshes the list (the secret stays only in the mutation's result). */
export const useCreateToken = (): UseMutationResult<CreatedToken, Error, CreateTokenRequest> => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createToken,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TOKENS_QUERY_KEY }),
  });
};

/** Revokes a token and refreshes the list. */
export const useRevokeToken = (): UseMutationResult<void, Error, string> => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: revokeToken,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TOKENS_QUERY_KEY }),
  });
};
