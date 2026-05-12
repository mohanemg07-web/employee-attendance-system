import { useState } from "react";
import { format } from "date-fns";
import { CheckCircle2 } from "lucide-react";
import api from "../api/client";
import UploadCard from "../components/admin-panel/UploadCard";
import ImportSummary from "../components/admin-panel/ImportSummary";

export default function AdminPanel() {
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadMeta, setUploadMeta] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  async function uploadFile(file) {
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    setUploadMeta(null);

    try {
      const form = new FormData();
      form.append("file", file);

      const res = await api.post("/admin/upload-csv", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const d = res?.data ?? {};
      setUploadResult(d);
      setUploadMeta({
        file_name: d?.filename ?? file?.name,
        uploaded_at: format(new Date(), "yyyy-MM-dd HH:mm:ss"),
      });
    } catch (e) {
      setUploadError(e?.response?.data?.detail || e?.message || "Upload failed");
      throw e; // UploadCard handles the error state
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 space-y-3 animate-in fade-in duration-500 pb-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Admin Panel</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">Import attendance data via CSV upload</p>
      </div>

      {/* Upload Card */}
      <UploadCard onUpload={uploadFile} />

      {/* Upload progress */}
      {uploading && (
        <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/10 px-3 py-2 text-xs text-muted-foreground">
          <svg className="h-3.5 w-3.5 animate-spin text-primary" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span>Processing…</span>
        </div>
      )}

      {/* Error */}
      {uploadError && !uploading && (
        <div className="rounded-md border border-rose-500/20 bg-rose-500/5 px-3 py-2 text-xs text-rose-700">
          Upload failed: {String(uploadError)}
        </div>
      )}

      {/* Success + file info */}
      {uploadMeta?.file_name && !uploading && (
        <div className="flex items-center gap-2 rounded-md border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-700">
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
          <span className="font-medium">{uploadMeta.file_name}</span>
          <span className="text-muted-foreground">· {uploadMeta.uploaded_at}</span>
        </div>
      )}

      {/* Import Summary */}
      {uploadResult && !uploading && (
        <ImportSummary summary={uploadResult} />
      )}
    </div>
  );
}
