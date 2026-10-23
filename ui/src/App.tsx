import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Check, Download, Loader2, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

const TOKEN =
  (window as unknown as { PATCHER_TOKEN?: string }).PATCHER_TOKEN ?? "";

type Phase = "idle" | "uploading" | "patching" | "done" | "error";

const PHASES: Record<string, string> = {
  starting: "Starting",
  inspect: "Inspecting",
  read: "Reading binary",
  steps: "Applying patches",
  plist: "Updating Info.plist",
  write: "Writing IPA",
  verify: "Verifying",
  done: "Done",
};

interface UploadResult {
  ok: boolean;
  upload: string;
  name: string;
  size: number;
  version: string;
}

interface JobSnapshot {
  id: string;
  state: "running" | "done" | "error" | "cancelled";
  phase: string;
  pct: number;
  detail: string;
  error: string | null;
  result: { out?: string; out_name?: string } | null;
}

const mb = (n: number) => `${(n / 1e6).toFixed(1)} MB`;

function uploadFile(
  file: File,
  onProgress: (fraction: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.setRequestHeader("X-Patch-Token", TOKEN);
    xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      let data: (UploadResult & { error?: string }) | null = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        reject(new Error(`Upload failed (HTTP ${xhr.status})`));
        return;
      }
      if (!data || data.ok === false) {
        reject(new Error(data?.error ?? `Upload failed (HTTP ${xhr.status})`));
        return;
      }
      resolve(data);
    };
    xhr.onerror = () =>
      reject(new Error("Upload failed — is the server still running?"));
    xhr.onabort = () => reject(new Error("Upload cancelled"));
    xhr.send(file);
  });
}

async function startPatch(upload: string): Promise<JobSnapshot> {
  const res = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Patch-Token": TOKEN },
    body: JSON.stringify({ upload }),
  });
  const data = await res.json().catch(() => null);
  if (!data || data.ok === false) {
    throw new Error(data?.error ?? `HTTP ${res.status}`);
  }
  return data.job as JobSnapshot;
}

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [pct, setPct] = useState(0);
  const [detail, setDetail] = useState("");
  const [error, setError] = useState("");
  const [outName, setOutName] = useState("");
  const [jobId, setJobId] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => () => esRef.current?.close(), []);

  const reset = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setPhase("idle");
    setPct(0);
    setDetail("");
    setError("");
    setOutName("");
    setJobId("");
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
  }, []);

  const watch = useCallback((job: JobSnapshot) => {
    esRef.current?.close();
    const es = new EventSource(
      `/api/job/${job.id}/events?token=${encodeURIComponent(TOKEN)}`,
    );
    esRef.current = es;
    es.onmessage = (event) => {
      let data: any;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (data.done) {
        es.close();
        esRef.current = null;
        const snap = data.job as JobSnapshot;
        if (snap.state === "done") {
          const name =
            snap.result?.out_name ?? snap.result?.out?.split("/").pop() ?? "";
          setOutName(name);
          setJobId(snap.id);
          setPct(100);
          setDetail("");
          setPhase("done");
        } else {
          setError(snap.error ?? "Patch failed");
          setPhase("error");
        }
        return;
      }
      setPct(45 + Math.max(0, Math.min(100, data.pct ?? 0)) * 0.55);
      const label = PHASES[data.phase] ?? data.phase ?? "";
      setDetail(data.detail ? `${label} · ${data.detail}` : label);
    };
    es.onerror = () => {
      /* the server closes the stream when the job finishes */
    };
  }, []);

  const runPatch = useCallback(async () => {
    if (!file || phase === "uploading" || phase === "patching") return;
    setPhase("uploading");
    setError("");
    setPct(0);
    setDetail("Uploading…");
    try {
      const uploaded = await uploadFile(file, (fraction) => {
        setPct(fraction * 45);
        setDetail("Uploading the IPA…");
      });
      setDetail("Starting…");
      const job = await startPatch(uploaded.upload);
      setPhase("patching");
      setPct(45);
      watch(job);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  }, [file, phase, watch]);

  const busy = phase === "uploading" || phase === "patching";
  const downloadUrl = jobId
    ? `/api/download/${jobId}?token=${encodeURIComponent(TOKEN)}`
    : "#";

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
                {outName}
              </p>
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

              <Button
                data-testid="patch-button"
                className="mt-2.5 h-10 w-full"
                onClick={() => void runPatch()}
                disabled={!file || busy}
              >
                {busy ? (
                  <>
                    <Loader2 className="animate-spin" />
                    {phase === "uploading" ? "Uploading" : "Patching"}
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
                Files are processed locally and never leave this machine. The
                original IPA is not modified.
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default App;
