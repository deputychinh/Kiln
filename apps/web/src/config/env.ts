/**
 * The only place the web app reads build-time environment (`.env.example`).
 *
 * Empty by default: the app calls the API on its own origin (`/api/v1/…`), which Vite's dev and
 * preview servers proxy to the API (KILN-12). The session cookie is then first-party and
 * `SameSite=Lax`, whichever host name the browser used.
 */
export const apiBaseUrl = (): string => String(import.meta.env.VITE_KILN_API_URL ?? '');
