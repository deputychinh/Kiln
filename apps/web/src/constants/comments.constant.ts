/** The API's limit on one comment (KILN-10); the field stops at it. */
export const COMMENT_BODY_MAX_LENGTH = 2000;
/** Threads and replies per request (the API allows 1 to 100). */
export const COMMENT_PAGE_LIMIT = 50;
export const threadsQueryKey = (versionId: string) => ['comment-threads', versionId] as const;
export const repliesQueryKey = (threadId: string) => ['comment-replies', threadId] as const;
/** A drag shorter than this (in image fractions, on both axes) marks a point, not a rectangle. */
export const REGION_MIN_DRAG = 0.02;
/** One arrow-key step when moving or resizing a region from the keyboard; Alt takes a fine step. */
export const REGION_KEY_STEP = 0.02;
export const REGION_FINE_STEP = 0.005;
/** The smallest rectangle the keyboard can make. */
export const REGION_MIN_SIZE = 0.02;
/** Where a region marked from the keyboard starts: a centred rectangle. */
export const REGION_START = { shape: 'rect', x: 0.3, y: 0.3, width: 0.4, height: 0.4 } as const;
/** How much of a comment names its region ("Region 2: The rim is too…"). */
export const REGION_LABEL_EXCERPT = 40;
/** A mark's numbered target on the image: 24 px (WCAG 2.5.8), kept this far apart. */
export const BADGE_SIZE_PX = 24;
export const BADGE_GAP_PX = 2;
/** How many rings of neighbouring places a crowded badge tries before staying put. */
export const BADGE_SEARCH_RINGS = 6;
