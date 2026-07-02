import { CheckCircle, CircleDashed, Spinner, XCircle } from "@phosphor-icons/react";
import type { JobStatus } from "../types/recipe";
import { staggerStyle } from "../lib/motion";

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
  { label: "Refining recipe details", statuses: ["refining"] },
];

const ORDER: JobStatus[] = [
  "queued", "downloading", "downloaded", "transcribing", "transcribed",
  "extracting", "extracted", "extracting_frames", "frames_done", "ocr", "refining", "done",
];

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s elapsed` : `${s}s elapsed`;
}

interface ProgressViewProps {
  status: JobStatus | null;
  message: string | null;
  error: string | null;
  elapsedSeconds?: number;
}

export function ProgressView({ status, message, error, elapsedSeconds }: ProgressViewProps) {
  const currentIndex = status ? ORDER.indexOf(status) : -1;

  return (
    <div className="flex w-full max-w-[420px] flex-col items-center gap-4">
      {MILESTONES.map((milestone, i) => {
        const milestoneIndex = ORDER.indexOf(milestone.statuses[0]);
        const isActive = status !== null && milestone.statuses.includes(status);
        const isComplete = currentIndex > ORDER.indexOf(milestone.statuses[milestone.statuses.length - 1]);
        const isFailed = status === "failed" && currentIndex <= milestoneIndex && !isComplete;

        return (
          <div
            key={milestone.label}
            className="animate-fade-in-up flex w-full items-center justify-center gap-3"
            style={staggerStyle(i)}
          >
            {isFailed && error ? (
              <XCircle size={22} weight="fill" className="shrink-0 text-danger" />
            ) : isComplete ? (
              <CheckCircle size={22} weight="fill" className="shrink-0 text-accent" />
            ) : isActive ? (
              <Spinner size={22} weight="bold" className="shrink-0 animate-spin text-accent" />
            ) : (
              <CircleDashed size={22} className="shrink-0 text-text-faint" />
            )}
            <span className={isActive || isComplete ? "text-[17px] text-text" : "text-[17px] text-text-muted"}>
              {milestone.label}
            </span>
          </div>
        );
      })}
      {message && !error && <p className="mt-2 text-center text-[14px] text-text-muted">{message}</p>}
      {typeof elapsedSeconds === "number" && !error && (
        <p className="font-mono text-[13px] text-text-faint">{formatElapsed(elapsedSeconds)}</p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-center text-[14px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
