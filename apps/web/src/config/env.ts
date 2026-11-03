/** The only place the web app reads build-time environment (`.env.example`). */
export const apiBaseUrl = (): string =>
  String(import.meta.env.VITE_KILN_API_URL ?? 'http://127.0.0.1:8000');
