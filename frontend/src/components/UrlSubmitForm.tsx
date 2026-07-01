import { useState } from "react";
import { Link, Spinner } from "@phosphor-icons/react";
import { Button } from "./ui/Button";

interface UrlSubmitFormProps {
  onSubmit: (url: string) => void;
  submitting: boolean;
  error: string | null;
}

export function UrlSubmitForm({ onSubmit, submitting, error }: UrlSubmitFormProps) {
  const [url, setUrl] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) onSubmit(url.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="flex w-full max-w-[560px] flex-col gap-3">
      <label htmlFor="video-url" className="text-[14px] font-medium text-ink-muted-80">
        YouTube Short or Instagram Reel URL
      </label>
      <div className="flex items-center gap-2 rounded-full border border-hairline bg-white px-5 py-3 focus-within:border-primary">
        <Link size={18} weight="bold" className="shrink-0 text-ink-muted-48" />
        <input
          id="video-url"
          type="url"
          inputMode="url"
          placeholder="https://www.youtube.com/shorts/..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="w-full bg-transparent text-[17px] text-ink outline-none placeholder:text-ink-muted-48"
          required
        />
      </div>
      {error && (
        <p role="alert" className="text-[14px] text-red-600">
          {error}
        </p>
      )}
      <Button type="submit" disabled={submitting || !url.trim()} className="self-start">
        {submitting ? (
          <span className="flex items-center gap-2">
            <Spinner size={18} className="animate-spin" weight="bold" />
            Extracting...
          </span>
        ) : (
          "Extract recipe"
        )}
      </Button>
    </form>
  );
}
