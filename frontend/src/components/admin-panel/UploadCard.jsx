import { useMemo, useRef, useState } from "react";
import { UploadCloud, LoaderCircle, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent } from "../ui/card";
import { cn } from "../../lib/utils";

const MAX_BYTES = 20 * 1024 * 1024;
const ACCEPT_EXT = ["csv", "xlsx", "xls"];

function fmtBytes(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return `${(v / (1024 * 1024)).toFixed(1)}MB`;
}

export default function UploadCard({ onUpload }) {
  const inputRef = useRef(null);
  const [drag, setDrag] = useState(false);
  const [state, setState] = useState("idle");
  const [message, setMessage] = useState("");

  const Icon = useMemo(() => {
    if (state === "uploading") return LoaderCircle;
    if (state === "success") return CheckCircle2;
    if (state === "error") return XCircle;
    return UploadCloud;
  }, [state]);

  async function handleFile(file) {
    if (!file) return;
    const ext = String(file.name || "").split(".").pop()?.toLowerCase();
    if (!ACCEPT_EXT.includes(ext)) {
      setState("error");
      setMessage("Invalid format. Use CSV or XLSX.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setState("error");
      setMessage(`Too large (${fmtBytes(file.size)}). Max 20MB.`);
      return;
    }
    setMessage("");
    setState("uploading");
    try {
      await onUpload?.(file);
      setState("success");
      setMessage("Import completed successfully.");
    } catch (e) {
      setState("error");
      setMessage(e?.message || "Upload failed.");
    }
  }

  return (
    <Card className="rounded-xl shadow-sm">
      <CardContent className="p-4 space-y-2">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Upload Attendance File
        </div>

        {/* Drop zone — compact */}
        <div
          className={cn(
            "flex items-center gap-4 rounded-lg border-2 border-dashed border-border bg-card px-4 py-3 transition-colors",
            drag && "border-primary/60 bg-secondary/20"
          )}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files?.[0]); }}
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-secondary/50 text-muted-foreground">
            <Icon className={cn("h-4 w-4", state === "uploading" && "animate-spin")} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-foreground">Drag and drop file here</div>
            <div className="text-[11px] text-muted-foreground">CSV, XLSX · Max 20MB</div>
          </div>

          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className={cn(
              "shrink-0 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground shadow-sm",
              "transition-colors hover:bg-secondary/30",
              state === "uploading" && "pointer-events-none opacity-60"
            )}
          >
            Choose File
          </button>

          <input
            ref={inputRef}
            type="file"
            hidden
            accept=".csv,.xlsx,.xls"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
        </div>

        {/* Status message — compact */}
        {message ? (
          <div
            className={cn(
              "rounded-md px-3 py-1.5 text-xs",
              state === "success" && "border border-emerald-500/20 bg-emerald-500/5 text-emerald-700",
              state === "error" && "border border-rose-500/20 bg-rose-500/5 text-rose-700",
              state === "uploading" && "border border-border bg-secondary/10 text-muted-foreground",
              state === "idle" && "border border-border bg-secondary/10 text-muted-foreground"
            )}
          >
            {message}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
