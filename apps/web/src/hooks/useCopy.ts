import type { Copy } from '@/interfaces/copy.interface';
import { en } from '@/locales/en';
import { vi } from '@/locales/vi';

/** English is the source; Vietnamese when the browser prefers it. */
export const useCopy = (): Copy => (navigator.language.startsWith('vi') ? vi : en);
