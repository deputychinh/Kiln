/** A failed API call: `status` 0 means the API could not be reached at all. */
export interface ApiError extends Error {
  name: 'ApiError';
  status: number;
  /** The stable `code` from RFC 9457 problem details, when the API sent one. */
  code: string | null;
  /** On a review conflict, the state the version is in now (`current_state`, KILN-11). */
  currentState: string | null;
}
