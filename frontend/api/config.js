/**
 * Single place that decides where HTTP requests go.
 * Port to TypeScript as-is; no UI logic here.
 *
 * Precedence (see docs/FE_BE_INTEGRATION.md):
 * 1. import.meta.env.VITE_API_BASE (Vite build / .env)
 * 2. window.API_BASE (optional nginx inject in production static HTML)
 * 3. Dev default: "/api" (Vite proxy → FastAPI)
 * 4. Production static build without proxy: direct FastAPI URL
 */
export function getApiBase() {
  const vite = import.meta.env.VITE_API_BASE;
  if (vite !== undefined && vite !== null && String(vite).length > 0) {
    return String(vite);
  }
  if (typeof window !== "undefined" && window.API_BASE) {
    return window.API_BASE;
  }
  if (import.meta.env.DEV) {
    return "/api";
  }
  return "http://localhost:8000";
}
