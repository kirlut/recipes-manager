import { useState } from "react";
import { uploadImage } from "../api/uploads";
import { ApiError } from "../api/client";

interface ImageUploadProps {
  value: string | null;
  onChange: (filename: string | null) => void;
}

export function ImageUpload({ value, onChange }: ImageUploadProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null);
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const res = await uploadImage(file);
      onChange(res.filename);
    } catch (err) {
      const msg = err instanceof ApiError ? err.problem.detail || err.problem.title : String(err);
      setError(msg ?? "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="form-control">
      <label className="label">
        <span className="label-text">Image</span>
      </label>
      <input
        type="file"
        accept="image/jpeg,image/png"
        className="file-input file-input-bordered"
        onChange={handleChange}
        disabled={busy}
      />
      {value && (
        <div className="mt-2">
          <img
            src={`/uploads/${value}`}
            alt=""
            className="max-h-32 rounded border"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
          <div className="text-xs opacity-70 mt-1">{value}</div>
        </div>
      )}
      {error && <div className="text-error text-sm mt-1">{error}</div>}
    </div>
  );
}
