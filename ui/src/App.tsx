import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Check, Download, Loader2, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { patchIpa } from "@/lib/engine";
import type { RandomAccess } from "@/lib/engine";
import { ADDITIONS, MANIFEST } from "@/lib/manifest";

type Phase = "idle" | "patching" | "done" | "error";

const PHASES: Record<string, string> = {
  inspect: "Inspecting",
  read: "Reading binary",
  verify: "Verifying",
  steps: "Applying patches",
  plist: "Updating Info.plist",
  write: "Writing IPA",
  done: "Done",
};

const mb = (n: number) => `${(n / 1e6).toFixed(1)} MB`;

const PROFILES = MANIFEST.profiles ?? [];
const DEFAULT_PROFILE =
  PROFILES.find((profile) => profile.default) ?? PROFILES[0];

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [profileId, setProfileId] = useState(DEFAULT_PROFILE?.id ?? "");
  const [outProfile, setOutProfile] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [pct, setPct] = useState(0);
  const [detail, setDetail] = useState("");
  const [error, setError] = useState("");
  const [outName, setOutName] = useState("");
  const [outSize, setOutSize] = useState(0);
  const [downloadUrl, setDownloadUrl] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const urlRef = useRef("");

  const clearUrl = useCallback(() => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = "";
    }
  }, []);

  useEffect(() => () => clearUrl(), [clearUrl]);

  const reset = useCallback(() => {
    clearUrl();
    setPhase("idle");
    setPct(0);
    setDetail("");
    setError("");
    setOutName("");
    setOutSize(0);
    setOutProfile("");
    setDownloadUrl("");
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
  }, [clearUrl]);

  const runPatch = useCallback(async () => {
    if (!file || phase === "patching") return;
    clearUrl();
    setPhase("patching");
    setPct(0);
    setDetail("Reading IPA…");
    setError("");
    try {
      const source: RandomAccess = {
        size: file.size,
        read: async (offset, length) =>
          new Uint8Array(await file.slice(offset, offset + length).arrayBuffer()),
        slice: (offset, length) => file.slice(offset, offset + length),
      };
      const parts: BlobPart[] = [];
      const result = await patchIpa(
        source,
        (part) => {
          parts.push(part as BlobPart);
        },
        MANIFEST,
        {
          profile: profileId || undefined,
          additions: ADDITIONS,
          onEvent: (event) => {
            setPct(event.pct);
            const label = PHASES[event.phase] ?? event.phase;
            setDetail(event.detail ? `${label} · ${event.detail}` : label);
          },
        },
      );
      const blob = new Blob(parts, { type: "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      setDownloadUrl(url);
      setOutName(result.outName);
      setOutSize(result.size);
      setOutProfile(result.profileLabel ?? "");
      setPct(100);
      setDetail("");
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  }, [file, phase, clearUrl, profileId]);

  const busy = phase === "patching";

  return (
    <div className="flex min-h-dvh items-center justify-center bg-white p-6 text-neutral-950">
      <Card className="w-full max-w-[520px] gap-0 rounded-2xl border-neutral-200 py-0 shadow-none">
        <CardContent className="p-7">
          {phase === "done" ? (
            <div
              data-testid="done"
              className="flex flex-col items-center py-2 text-center"
            >
              <div className="grid size-11 place-items-center rounded-full border border-neutral-300">
                <Check className="size-5" strokeWidth={2.5} />
              </div>
              <h1 className="mt-4 text-[15px] font-semibold tracking-tight">
                Patch complete
              </h1>
              <p className="mt-1.5 max-w-full break-all font-mono text-[12px] leading-relaxed text-neutral-500">
                {outName} · {mb(outSize)}
              </p>
              {outProfile && (
                <p className="mt-1 text-[11.5px] text-neutral-400">
                  {outProfile}
                </p>
              )}
              <div className="mt-5 flex gap-2">
                <Button asChild data-testid="download-button">
                  <a href={downloadUrl} download={outName}>
                    <Download />
                    Download IPA
                  </a>
                </Button>
                <Button variant="ghost" onClick={reset}>
                  Patch another
                </Button>
              </div>
              <p className="mt-4 text-[11.5px] leading-relaxed text-neutral-400">
                Install with AltStore, Sideloadly or TrollStore — the IPA gets
                re-signed on install.
              </p>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <h1 className="text-[15px] font-semibold tracking-tight">
                  MHFU Patcher
                </h1>
              </div>

              <input
                ref={inputRef}
                data-testid="file-input"
                type="file"
                accept=".ipa,application/octet-stream"
                className="sr-only"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setError("");
                  if (phase === "error") setPhase("idle");
                }}
              />

              <div className="flex items-center gap-2">
                <Button
                  data-testid="choose-button"
                  variant="outline"
                  className="h-10 shrink-0"
                  onClick={() => inputRef.current?.click()}
                  disabled={busy}
                >
                  <Upload />
                  Choose IPA
                </Button>
                {file ? (
                  <div className="flex min-w-0 flex-1 items-center gap-1 text-[12px] text-neutral-500">
                    <span className="truncate">{file.name}</span>
                    <span className="shrink-0 text-neutral-400">
                      · {mb(file.size)}
                    </span>
                    {!busy && (
                      <button
                        type="button"
                        aria-label="Remove file"
                        className="ml-1 shrink-0 text-neutral-400 hover:text-neutral-900"
                        onClick={reset}
                      >
                        <X className="size-3.5" />
                      </button>
                    )}
                  </div>
                ) : (
                  <span className="text-[12px] text-neutral-400">
                    No file selected
                  </span>
                )}
              </div>

              {PROFILES.length > 0 && (
                <div className="mt-5">
                  <div className="mb-2 flex items-baseline justify-between">
                    <span className="text-[12px] font-medium">iPhone model</span>
                    <span className="text-[11px] text-neutral-400">Pick one</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {PROFILES.map((profile) => {
                      const selected = profileId === profile.id;
                      return (
                        <Button
                          key={profile.id}
                          type="button"
                          variant={selected ? "default" : "outline"}
                          aria-pressed={selected}
                          disabled={busy}
                          className="h-auto min-h-10 flex-col items-start justify-center gap-0 whitespace-normal px-2.5 py-1.5 text-left"
                          onClick={() => {
                            setProfileId(profile.id);
                            setError("");
                          }}
                        >
                          <span className="text-[11.5px] leading-tight font-medium">
                            {profile.label}
                          </span>
                        </Button>
                      );
                    })}
                  </div>
                </div>
              )}

              <Button
                data-testid="patch-button"
                className="mt-2.5 h-10 w-full"
                onClick={() => void runPatch()}
                disabled={!file || busy || (PROFILES.length > 0 && !profileId)}
              >
                {busy ? (
                  <>
                    <Loader2 className="animate-spin" />
                    Patching
                  </>
                ) : (
                  "Patch"
                )}
              </Button>

              {busy && (
                <div data-testid="progress" className="mt-5 space-y-2">
                  <Progress value={pct} />
                  <div className="flex items-baseline justify-between gap-4 text-[11.5px] text-neutral-500">
                    <span className="truncate">{detail || "Working…"}</span>
                    <span className="tabular-nums">{Math.round(pct)}%</span>
                  </div>
                </div>
              )}

              {phase === "error" && (
                <div
                  data-testid="error"
                  className="mt-4 flex items-start gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-2.5 text-[12.5px] leading-relaxed text-neutral-800"
                >
                  <AlertCircle className="mt-px size-4 shrink-0" />
                  <span className="break-words whitespace-pre-wrap">
                    {error}
                  </span>
                </div>
              )}

              <p className="mt-4 text-[11.5px] leading-relaxed text-neutral-400">
                Everything runs in this browser tab — the IPA is never uploaded.
                The original file is not modified.
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default App;
