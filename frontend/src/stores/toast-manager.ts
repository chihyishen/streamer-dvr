import type { ToastItem } from "../types";

let toastId = 0;

export function formatApiError(error: unknown) {
  if (!(error instanceof Error)) {
    return "Request failed";
  }
  try {
    const payload = JSON.parse(error.message) as { detail?: string };
    return payload.detail || "Request failed";
  } catch {
    return error.message || "Request failed";
  }
}

export function createToast(tone: "success" | "error", message: string): ToastItem {
  return {
    id: ++toastId,
    tone,
    message,
  };
}
