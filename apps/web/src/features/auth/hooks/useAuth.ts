import {
  useMutation,
  type UseMutationResult,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';

import { ME_QUERY_KEY } from '@/constants/auth.constant';
import { signIn, signOut } from '@/features/auth/services/auth.service';
import { meQueryOptions } from '@/features/auth/services/me.query';
import type { Me } from '@/interfaces/auth.interface';

/** The signed-in user (cached; the route guard loads it first). */
export const useMe = (): UseQueryResult<Me> => useQuery(meQueryOptions());

/** Signs in; on success the user is cached so the guard lets the next page through at once. */
export const useSignIn = (): UseMutationResult<Me, Error, { email: string; password: string }> => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ email, password }) => signIn(email, password),
    onSuccess: (me) => {
      queryClient.removeQueries(); // nothing cached for someone else survives a new session
      queryClient.setQueryData(ME_QUERY_KEY, me);
    },
  });
};

/** Signs out; every cached answer belonged to that session, so the cache is emptied. */
export const useSignOut = (): UseMutationResult<void, Error, void> => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: signOut,
    onSuccess: () => queryClient.clear(),
  });
};
