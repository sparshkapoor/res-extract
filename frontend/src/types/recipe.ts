// Mirrors backend/app/models.py — kept in sync by hand for this MVP (no
// codegen step; the two are small enough that drift is easy to spot).

export type Platform = "youtube" | "instagram";

export type JobStatus =
  | "queued"
  | "downloading"
  | "downloaded"
  | "transcribing"
  | "transcribed"
  | "extracting"
  | "extracted"
  | "extracting_frames"
  | "frames_done"
  | "ocr"
  | "done"
  | "failed";

export interface Ingredient {
  name: string;
  quantity: string | null;
  unit: string | null;
  is_estimated: boolean;
  name_is_generic: boolean;
}

export interface Step {
  index: number;
  instruction: string;
  verbatim_transcript_citation: string;
  timestamp_seconds: number | null;
  image_path: string | null;
}

export interface Recipe {
  title: string;
  source_url: string;
  platform: Platform;
  ingredients: Ingredient[];
  steps: Step[];
  cook_time_minutes: number | null;
  servings: number | null;
  calories: number | null;
  oven_temp_f: number | null;
}

export interface JobCreateResponse {
  job_id: string;
  status: JobStatus;
  cached: boolean;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  stage_message: string | null;
  error: string | null;
  updated_at: string;
}

export interface JobEvent {
  stage: JobStatus;
  status: "in_progress" | "success" | "failed";
  message: string | null;
}

export interface SavedRecipeSummary {
  url_hash: string;
  url: string;
  title: string;
  platform: Platform;
  thumbnail: string | null;
  created_at: string;
}
