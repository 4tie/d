export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parseMaybeJson(res: Response): Promise<unknown> {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return res.text();
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    const detail = await parseMaybeJson(res);
    throw new ApiError(`GET ${path} failed`, res.status, detail);
  }

  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });

  if (!res.ok) {
    const detail = await parseMaybeJson(res);
    throw new ApiError(`POST ${path} failed`, res.status, detail);
  }

  return (await res.json()) as T;
}

export function formatApiError(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.detail;
    if (d && typeof d === "object" && "detail" in d) {
      try {
        return String((d as any).detail);
      } catch {
        return `${err.message} (HTTP ${err.status})`;
      }
    }
    return `${err.message} (HTTP ${err.status})`;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}
