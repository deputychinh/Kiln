/**
 * The API the journeys use. `KILN_API_PORT` moves it off 8000 when another program holds that
 * port; the preview server's `/api` proxy follows it (`KILN_API_PROXY_TARGET`).
 */
export const API_PORT = process.env.KILN_API_PORT ?? '8000';
export const API_URL = `http://127.0.0.1:${API_PORT}`;
