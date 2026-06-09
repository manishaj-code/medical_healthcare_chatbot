export interface ChatAttachment {
  type: "report";
  report_id?: string;
  filename: string;
  size_bytes?: number;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileExt(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() || "";
}

function fileIcon(filename: string): string {
  const ext = fileExt(filename);
  if (ext === "pdf") return "picture_as_pdf";
  if (["png", "jpg", "jpeg", "webp", "gif"].includes(ext)) return "image";
  if (ext === "docx") return "description";
  if (["xlsx", "csv", "tsv"].includes(ext)) return "table_chart";
  if (["txt", "md", "json", "xml", "html", "htm"].includes(ext)) return "article";
  return "attach_file";
}

function fileKindLabel(filename: string): string {
  const ext = fileExt(filename);
  if (ext === "pdf") return "PDF report";
  if (["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"].includes(ext)) return "Image scan";
  if (ext === "docx") return "Word document";
  if (["xlsx", "csv", "tsv"].includes(ext)) return "Spreadsheet report";
  if (["txt", "md", "json", "xml", "html", "htm"].includes(ext)) return "Text report";
  return "Medical file";
}

function fileIconTone(filename: string): string {
  const ext = fileExt(filename);
  if (ext === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"].includes(ext)) return "image";
  if (ext === "docx") return "doc";
  if (["xlsx", "csv", "tsv"].includes(ext)) return "sheet";
  return "default";
}

const LEGACY_UPLOAD_RE = /I've uploaded my medical report \(([^)]+)\)/i;
const AUTO_REPORT_PROMPT_RE =
  /^please analyze (this|it|my).*(report|document|file|results?)/i;

export function parseLegacyUploadAttachment(content: string): ChatAttachment | undefined {
  const match = content.match(LEGACY_UPLOAD_RE);
  if (!match) return undefined;
  return { type: "report", filename: match[1].trim() };
}

export function userMessageCaption(content: string, hasAttachment: boolean): string | null {
  if (!hasAttachment) return content.trim() || null;
  let stripped = content.replace(LEGACY_UPLOAD_RE, "").replace(/^\.\s*/, "").trim();
  if (AUTO_REPORT_PROMPT_RE.test(stripped)) return null;
  return stripped || null;
}

interface Props {
  attachment: ChatAttachment;
  variant?: "user" | "ai" | "upload";
  showView?: boolean;
  onView?: () => void;
}

export default function ChatFileAttachment({
  attachment,
  variant = "user",
  showView = false,
  onView,
}: Props) {
  const isUpload = variant === "upload";
  const isAi = variant === "ai";
  const kind = isAi ? "Clinical Analysis" : fileKindLabel(attachment.filename);
  const size = attachment.size_bytes ? formatFileSize(attachment.size_bytes) : null;
  const tone = fileIconTone(attachment.filename);

  return (
    <div
      className={`chat-file-attachment chat-file-attachment--${isUpload ? "upload" : variant} chat-file-attachment--tone-${tone}`}
    >
      {isUpload && <span className="chat-file-attachment-kicker">Uploaded report</span>}
      <div className="chat-file-attachment-row">
        <div className="chat-file-attachment-icon" aria-hidden="true">
          <span className="material-symbols-outlined">{fileIcon(attachment.filename)}</span>
        </div>
        <div className="chat-file-attachment-meta">
          <strong title={attachment.filename}>{attachment.filename}</strong>
          <span>
            {kind}
            {size ? ` · ${size}` : ""}
          </span>
        </div>
        {showView ? (
          <button
            type="button"
            className="chat-file-attachment-view"
            onClick={onView}
            disabled={!onView}
          >
            View
          </button>
        ) : isUpload ? (
          <span className="chat-file-attachment-pill">Ready</span>
        ) : (
          <span className="material-symbols-outlined chat-file-attachment-badge" title="Uploaded">
            check_circle
          </span>
        )}
      </div>
    </div>
  );
}
