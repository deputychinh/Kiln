import { useCallback, useEffect, useState } from 'react';

/**
 * Returns `request`: call it next to the state update that shows an error, and `focus` runs once
 * React has committed that update. Focusing in the same handler would land before the field is
 * `aria-invalid` and describes its error, so the error would not be read (KILN-48). Every call
 * focuses again, even when the error text is the same as last time. `focus` must be stable.
 */
export const useFocusAfterCommit = (focus: () => void): (() => void) => {
  const [requests, setRequests] = useState(0);
  useEffect(() => {
    if (requests > 0) focus();
  }, [requests, focus]);
  return useCallback(() => setRequests((count) => count + 1), []);
};
