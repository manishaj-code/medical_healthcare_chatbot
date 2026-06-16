export interface ParsedReportAnalysis {
  filename: string;
  summary: string | null;
  abnormal: { test?: string; value?: string; flag?: string }[];
  extension: string | null;
}

export function parseReportAnalysis(
  reportId: string,
  analysis: Record<string, unknown> | null | undefined,
): ParsedReportAnalysis {
  const data = analysis ?? {};
  const meta = (data._meta as Record<string, unknown> | undefined) ?? {};
  const filename =
    (typeof meta.filename === "string" && meta.filename) || `Report ${reportId.slice(0, 8).toUpperCase()}`;
  const summary = typeof data.summary === "string" ? data.summary.trim() : null;
  const abnormal = Array.isArray(data.abnormal)
    ? (data.abnormal as { test?: string; value?: string; flag?: string }[])
    : [];
  const extension = typeof meta.extension === "string" ? meta.extension : null;
  return { filename, summary, abnormal, extension };
}

export function reportFileIcon(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  if (ext === "pdf") return "picture_as_pdf";
  if (["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"].includes(ext)) return "image";
  if (ext === "docx") return "description";
  if (["xlsx", "csv", "tsv"].includes(ext)) return "table_chart";
  return "science";
}
