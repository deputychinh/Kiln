import { useEffect } from 'react';

/** Sets the tab title for a page ("Settings · Kiln"), so each view is announced and findable. */
export const useDocumentTitle = (title: string): void => {
  useEffect(() => {
    document.title = title;
  }, [title]);
};
