const AMZ_DATE = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/;

/** When a SigV4 presigned URL stops working (`X-Amz-Date` + `X-Amz-Expires`), or null if unknown. */
export const signedUrlExpiresAt = (url: string): number | null => {
  const params = new URL(url).searchParams;
  const date = AMZ_DATE.exec(params.get('X-Amz-Date') ?? '');
  const seconds = Number(params.get('X-Amz-Expires'));
  if (!date || !Number.isFinite(seconds) || seconds <= 0) return null;
  const [, year, month, day, hour, minute, second] = date.map(Number);
  if (year === undefined || month === undefined || day === undefined) return null;
  return Date.UTC(year, month - 1, day, hour, minute, second) + seconds * 1000;
};

const withoutQuery = (url: string): string => url.split('?', 1)[0] ?? url;

/**
 * The URL to show: the previous one while it points at the same object and stays valid for
 * `minRemainingMs`, so a re-signed URL does not make the browser download the image again.
 */
export const keepSignedUrl = ({
  previous,
  next,
  minRemainingMs,
  now = Date.now(),
}: {
  previous: string | null | undefined;
  next: string | null | undefined;
  minRemainingMs: number;
  now?: number;
}): string | null => {
  if (!previous || !next || withoutQuery(previous) !== withoutQuery(next)) return next ?? null;
  const expiresAt = signedUrlExpiresAt(previous);
  return expiresAt !== null && expiresAt - now >= minRemainingMs ? previous : next;
};
