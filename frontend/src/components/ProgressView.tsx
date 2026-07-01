import { CheckCircle, CircleDashed, Spinner, XCircle } from "@phosphor-icons/react";
import type { JobStatus } from "../types/recipe";

interface Milestone {
  label: string;
  statuses: JobStatus[];
}

const MILESTONES: Milestone[] = [
  { label: "Downloading video", statuses: ["queued", "downloading", "downloaded"] },
  { label: "Transcribing audio", statuses: ["transcribing", "transcribed"] },
  { label: "Extracting recipe", statuses: ["extracting", "extracted"] },
  { label: "Capturing step photos", statuses: ["extracting_frames", "frames_done"] },
  { label: "Reading on-screen text", statuses: ["ocr"] },
];

const ORDER: JobStatus[] = [
  "queued", "downloading", "downloaded", "transcribing", "transcribed",
  "extracting", "extracted", "extracting_frames", "frames_done", "ocr", "done",
];

interface ProgressViewProps {
  status: JobStatus | null;
  message: string | null;
  error: string | null;
}

export function ProgressView({ status, message, error }: ProgressViewProps) {
  const currentIndex = status ? ORDER.indexOf(status) : -1;

  return (
    <div className="flex w-full max-w-[420px] flex-col gap-4">
      {MILESTONES.map((milestone) => {
        const milestoneIndex = ORDER.indexOf(milestone.statuses[0]);
        const isActive = status !== null && milestone.statuses.includes(status);
        const isComplete = currentIndex > ORDER.indexOf(milestone.statuses[milestone.statuses.length - 1]);
        const isFailed = status === "failed" && currentIndex <= milestoneIndex && !isComplete;

        return (
          <div key={milestone.label} className="flex items-center gap-3">
            {isFailed && error ? (
              <XCircle size={22} weight="fill" className="shrink-0 text-red-600" />
            ) : isComplete ? (
              <CheckCircle size={22} weight="fill" className="shrink-0 text-primary" />
            ) : isActive ? (
              <Spinner size={22} weight="bold" className="shrink-0 animate-spin text-primary" />
            ) : (
              <CircleDashed size={22} className="shrink-0 text-ink-muted-48" />
            )}
            <span className={isActive || isComplete ? "text-[17px] text-ink" : "text-[17px] text-ink-muted-48"}>
              {milestone.label}
            </span>
          </div>
        );
      })}
      {message && !error && <p className="mt-2 text-[14px] text-ink-muted-48">{message}</p>}
      {error && (
        <p role="alert" className="mt-2 text-[14px] text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
