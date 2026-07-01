import { useEffect, useState } from "react";
import { BookmarkSimple } from "@phosphor-icons/react";
import { submitUrl, fetchResult, fetchSavedRecipe, ApiError } from "./api/client";
import { useJobStream } from "./hooks/useJobStream";
import { UrlSubmitForm } from "./components/UrlSubmitForm";
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

  const stream = useJobStream(phase === "processing" ? jobId : null);

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
          ? "flex min-h-[100dvh] w-full min-w-0 flex-col items-center overflow-x-hidden bg-surface-tile-1"
          : "safe-top safe-bottom flex min-h-[100dvh] w-full min-w-0 flex-col items-center overflow-x-hidden bg-canvas-parchment px-6 py-10"
      }
      style={
        !isDone
          ? {
              backgroundImage:
                "radial-gradient(ellipse 80% 50% at 50% -10%, rgba(0,124,240,0.16), transparent), radial-gradient(ellipse 60% 40% at 100% 10%, rgba(0,223,216,0.12), transparent)",
            }
          : undefined
      }
    >
      {phase !== "done" && (
        <header className="mb-10 flex w-full max-w-[420px] flex-col items-center gap-2 text-center">
          <h1 className="text-[40px] font-semibold leading-[1.1] tracking-[0] text-ink">res-extract</h1>
          <p className="w-full text-[17px] text-ink-muted-48">
            Paste a cooking Short or Reel — get the recipe, step by step.
          </p>
        </header>
      )}

      <main className="flex w-full min-w-0 flex-1 flex-col items-center">
        {(phase === "idle" || phase === "submitting" || phase === "error") && (
          <div className="flex w-full max-w-[560px] flex-col items-center gap-6">
            <UrlSubmitForm onSubmit={handleSubmit} submitting={phase === "submitting"} error={submitError} />
            {/* Generously spaced from the form above (gap-6) and sized as a
                real tap target (min-h-[44px]) so it's never fat-fingered
                against the submit button. */}
            <button
              type="button"
              onClick={() => setPhase("saved")}
              className="press-scale flex min-h-[44px] items-center gap-2 px-2 text-[15px] font-medium text-primary"
            >
              <BookmarkSimple size={18} weight="bold" />
              View saved recipes
            </button>
          </div>
        )}

        {phase === "saved" && (
          <div className="flex w-full max-w-[560px] flex-col gap-5">
            <button
              type="button"
              onClick={() => setPhase("idle")}
              className="press-scale flex min-h-[44px] items-center gap-1.5 self-start text-[14px] text-primary"
            >
              Back
            </button>
            <SavedRecipesList onSelect={handleSelectSaved} />
          </div>
        )}

        {phase === "processing" && (
          <ProgressView status={stream.status} message={stream.message} error={stream.error} />
        )}

        {phase === "done" && recipe && <RecipeCard recipe={recipe} onReset={handleReset} />}
      </main>
    </div>
  );
}

export default App;
