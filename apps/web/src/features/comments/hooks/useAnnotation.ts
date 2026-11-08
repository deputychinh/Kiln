import { useCallback, useMemo, useRef, useState } from 'react';

import type { Annotation, DraftRegion } from '@/interfaces/comment.interface';

/** The review state of one version: the chosen thread and the region being marked. */
export const useAnnotation = (): Annotation => {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [focusNonce, setFocusNonce] = useState(0);
  const [draft, setDraft] = useState<DraftRegion | null>(null);
  const [isMarking, setIsMarking] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const markButtonRef = useRef<HTMLButtonElement | null>(null);

  const setComposer = useCallback((element: HTMLTextAreaElement | null) => {
    composerRef.current = element;
  }, []);
  const setMarkButton = useCallback((element: HTMLButtonElement | null) => {
    markButtonRef.current = element;
  }, []);
  const focusComposer = useCallback(() => composerRef.current?.focus(), []);
  const focusMarkButton = useCallback(() => markButtonRef.current?.focus(), []);
  const select = useCallback((threadId: string | null, options?: { moveFocus?: boolean }) => {
    setSelectedThreadId(threadId);
    if (options?.moveFocus) setFocusNonce((nonce) => nonce + 1);
  }, []);
  const startMarking = useCallback((initial: DraftRegion) => {
    setDraft((current) => current ?? initial);
    setIsMarking(true);
  }, []);
  const stopMarking = useCallback((keep: boolean) => {
    setIsMarking(false);
    if (keep) {
      composerRef.current?.focus();
    } else {
      setDraft(null);
      markButtonRef.current?.focus();
    }
  }, []);
  const reset = useCallback(() => {
    setSelectedThreadId(null);
    setDraft(null);
    setIsMarking(false);
  }, []);

  return useMemo(
    () => ({
      selectedThreadId,
      focusNonce,
      select,
      draft,
      setDraft,
      isMarking,
      startMarking,
      stopMarking,
      setComposer,
      setMarkButton,
      focusComposer,
      focusMarkButton,
      reset,
    }),
    [
      selectedThreadId,
      focusNonce,
      select,
      draft,
      isMarking,
      startMarking,
      stopMarking,
      setComposer,
      setMarkButton,
      focusComposer,
      focusMarkButton,
      reset,
    ],
  );
};
