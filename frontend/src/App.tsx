import { useEffect, useState } from "react";
import { submitUrl, fetchResult, fetchSavedRecipe, ApiError } from "./api/client";
import { useJobStream } from "./hooks/useJobStream";
import { LandingHero } from "./components/LandingHero";
import { ProgressView } from "./components/ProgressView";
import { RecipeCard } from "./components/RecipeCard";
import { SavedRecipesList } from "./components/SavedRecipesList";
import type { Recipe } from "./types/recipe";

type Phase = "idle" | "submitting" | "processing" | "done" | "error" | "saved";

function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const stream = useJobStream(phase === "processing" ? jobId : null);

  // Client-side elapsed timer — avoids clock-skew issues a server-timestamp
  // comparison would have, and needs no backend support.
  useEffect(() => {
    if (phase !== "processing") {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const id = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [phase]);

  useEffect(() => {
    if (phase !== "processing" || !jobId) return;
    if (stream.status === "done") {
      fetchResult(jobId)
        .then((r) => {
          setRecipe(r);
          setPhase("done");
        })
        .catch((e) => {
          setSubmitError(e instanceof Error ? e.message : "Failed to load the extracted recipe.");
          setPhase("error");
        });
    } else if (stream.status === "failed") {
      setSubmitError(stream.error ?? "Recipe extraction failed.");
      setPhase("error");
    }
  }, [phase, jobId, stream.status, stream.error]);

  const handleSubmit = async (url: string) => {
    setSubmitError(null);
    setPhase("submitting");
    try {
      const res = await submitUrl(url);
      setJobId(res.job_id);
      if (res.cached && res.status === "done") {
        const r = await fetchResult(res.job_id);
        setRecipe(r);
        setPhase("done");
      } else {
        setPhase("processing");
      }
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : "Something went wrong submitting that URL.");
      setPhase("idle");
    }
  };

  const handleSelectSaved = async (urlHash: string) => {
    try {
      const r = await fetchSavedRecipe(urlHash);
      setRecipe(r);
      setPhase("done");
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Couldn't load that recipe.");
      setPhase("error");
    }
  };

  const handleReset = () => {
    setPhase("idle");
    setJobId(null);
    setRecipe(null);
    setSubmitError(null);
  };

  const isDone = phase === "done";

  return (
    <div
      className={
        isDone
          ? "ambient-glow flex min-h-[100dvh] w-full min-w-0 flex-col items-center overflow-x-hidden bg-canvas"
          : "ambient-glow safe-top safe-bottom flex min-h-[100dvh] w-full min-w-0 flex-col items-center overflow-x-hidden bg-canvas px-6 py-10"
      }
    >
      {(phase === "processing" || phase === "saved") && (
        <header className="animate-fade-in-up mb-10 flex w-full max-w-[420px] flex-col items-center gap-2 text-center">
          <h1 className="font-editorial text-[24px] font-semibold leading-[1.15] tracking-[-0.005em] text-text">
            res-extract
          </h1>
          <p className="w-full text-[15px] text-text-muted">
            Paste a cooking Short or Reel — get the recipe, step by step.
          </p>
        </header>
      )}

      <main className="flex w-full min-w-0 flex-1 flex-col items-center">
        {(phase === "idle" || phase === "submitting" || phase === "error") && (
          <LandingHero
            onSubmit={handleSubmit}
            submitting={phase === "submitting"}
            error={submitError}
            onViewSaved={() => setPhase("saved")}
            onSelectSaved={handleSelectSaved}
          />
        )}

        {phase === "saved" && (
          <div className="animate-fade-in-up flex w-full max-w-[560px] flex-col gap-5">
            <button
              type="button"
              onClick={() => setPhase("idle")}
              className="press-scale flex min-h-[44px] items-center gap-1.5 self-start text-[14px] text-accent"
            >
              Back
            </button>
            <SavedRecipesList onSelect={handleSelectSaved} />
          </div>
        )}

        {phase === "processing" && (
          <ProgressView
            status={stream.status}
            message={stream.message}
            error={stream.error}
            elapsedSeconds={elapsedSeconds}
          />
        )}

        {phase === "done" && recipe && <RecipeCard recipe={recipe} onReset={handleReset} />}
      </main>
    </div>
  );
}

export default App;
