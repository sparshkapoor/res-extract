import type { JobCreateResponse, JobStatusResponse, Recipe, SavedRecipeSummary } from "../types/recipe";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function submitUrl(url: string): Promise<JobCreateResponse> {
  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? res.statusText);
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export async function fetchJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) throw new ApiError(res.status, `Failed to fetch job status (${res.status})`);
  return res.json();
}

export async function fetchResult(jobId: string): Promise<Recipe> {
  const res = await fetch(`/api/jobs/${jobId}/result`);
  if (!res.ok) throw new ApiError(res.status, `Failed to fetch result (${res.status})`);
  return res.json();
}

export async function listSavedRecipes(): Promise<SavedRecipeSummary[]> {
  const res = await fetch("/api/recipes");
  if (!res.ok) throw new ApiError(res.status, `Failed to fetch saved recipes (${res.status})`);
  return res.json();
}

export async function fetchSavedRecipe(urlHash: string): Promise<Recipe> {
  const res = await fetch(`/api/recipes/${urlHash}`);
  if (!res.ok) throw new ApiError(res.status, `Failed to fetch saved recipe (${res.status})`);
  return res.json();
}

export { ApiError };
