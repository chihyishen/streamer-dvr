function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

function resolveApiOrigin() {
  const configured = (import.meta.env.VITE_API_ORIGIN as string | undefined)?.trim();
  if (configured) {
    return trimTrailingSlash(configured);
  }
  if (import.meta.env.DEV) {
    return "";
  }
  if (typeof window === "undefined") {
    return "";
  }
  return `${window.location.protocol}//${window.location.hostname}:8787`;
}

export const API_ORIGIN = resolveApiOrigin();

export function apiUrl(path: string) {
  return `${API_ORIGIN}${path}`;
}
