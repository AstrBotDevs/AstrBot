export interface AttachmentPresentationInput {
  type?: string;
  filename?: string;
  original_name?: string;
  embedded_file?: {
    filename?: string;
  };
}

export interface AttachmentPresentation {
  color: string;
  icon: string;
  label: string;
}

const fileTypeStyles: Record<string, AttachmentPresentation> = {
  pdf: { color: "#c43b3b", icon: "mdi-file-pdf-box", label: "PDF" },
  doc: { color: "#2b579a", icon: "mdi-file-word-box", label: "WORD" },
  docx: { color: "#2b579a", icon: "mdi-file-word-box", label: "WORD" },
  xls: { color: "#217346", icon: "mdi-file-excel-box", label: "XLS" },
  xlsx: { color: "#217346", icon: "mdi-file-excel-box", label: "XLSX" },
  csv: { color: "#217346", icon: "mdi-file-delimited-outline", label: "CSV" },
  ppt: { color: "#d24726", icon: "mdi-file-powerpoint-box", label: "PPT" },
  pptx: { color: "#d24726", icon: "mdi-file-powerpoint-box", label: "PPT" },
  jpg: { color: "#c1467a", icon: "mdi-file-image", label: "IMAGE" },
  jpeg: { color: "#c1467a", icon: "mdi-file-image", label: "IMAGE" },
  png: { color: "#c1467a", icon: "mdi-file-image", label: "IMAGE" },
  gif: { color: "#c1467a", icon: "mdi-file-image", label: "IMAGE" },
  webp: { color: "#c1467a", icon: "mdi-file-image", label: "IMAGE" },
  svg: { color: "#c1467a", icon: "mdi-svg", label: "SVG" },
  heic: { color: "#c1467a", icon: "mdi-file-image", label: "IMAGE" },
  bmp: { color: "#c1467a", icon: "mdi-file-image", label: "IMAGE" },
  mp3: { color: "#00897b", icon: "mdi-file-music-outline", label: "AUDIO" },
  wav: { color: "#00897b", icon: "mdi-file-music-outline", label: "AUDIO" },
  flac: { color: "#00897b", icon: "mdi-file-music-outline", label: "AUDIO" },
  m4a: { color: "#00897b", icon: "mdi-file-music-outline", label: "AUDIO" },
  ogg: { color: "#00897b", icon: "mdi-file-music-outline", label: "AUDIO" },
  mp4: { color: "#5e35b1", icon: "mdi-file-video-outline", label: "VIDEO" },
  mov: { color: "#5e35b1", icon: "mdi-file-video-outline", label: "VIDEO" },
  webm: { color: "#5e35b1", icon: "mdi-file-video-outline", label: "VIDEO" },
  zip: { color: "#8a6f00", icon: "mdi-folder-zip-outline", label: "ZIP" },
  rar: { color: "#8a6f00", icon: "mdi-folder-zip-outline", label: "RAR" },
  "7z": { color: "#8a6f00", icon: "mdi-folder-zip-outline", label: "7Z" },
  tar: { color: "#8a6f00", icon: "mdi-folder-zip-outline", label: "TAR" },
  gz: { color: "#8a6f00", icon: "mdi-folder-zip-outline", label: "GZ" },
  txt: { color: "#607d8b", icon: "mdi-file-document-outline", label: "TXT" },
  md: { color: "#607d8b", icon: "mdi-language-markdown-outline", label: "MD" },
  markdown: {
    color: "#607d8b",
    icon: "mdi-language-markdown-outline",
    label: "MD",
  },
};

const codeFileTypes = new Set([
  "c",
  "cc",
  "cpp",
  "cs",
  "css",
  "go",
  "h",
  "hpp",
  "html",
  "java",
  "js",
  "json",
  "jsx",
  "kt",
  "php",
  "py",
  "rb",
  "rs",
  "scss",
  "sh",
  "sql",
  "swift",
  "ts",
  "tsx",
  "vue",
  "xml",
  "yaml",
  "yml",
]);

export function attachmentName(part: AttachmentPresentationInput) {
  return (
    part.embedded_file?.filename ||
    part.original_name ||
    part.filename ||
    part.type ||
    "file"
  );
}

export function attachmentExtension(part: AttachmentPresentationInput) {
  const name = attachmentName(part);
  const extension = name.split(".").pop()?.toLowerCase() || "";
  return extension === name.toLowerCase() ? "" : extension;
}

export function attachmentPresentation(
  part: AttachmentPresentationInput,
): AttachmentPresentation {
  if (part.type === "image") {
    return { color: "#c1467a", icon: "mdi-file-image", label: "IMAGE" };
  }
  if (part.type === "record") {
    return { color: "#00897b", icon: "mdi-file-music-outline", label: "AUDIO" };
  }
  if (part.type === "video") {
    return { color: "#5e35b1", icon: "mdi-file-video-outline", label: "VIDEO" };
  }

  const extension = attachmentExtension(part);
  if (codeFileTypes.has(extension)) {
    return {
      color: "#6a4fb3",
      icon: extension === "json" ? "mdi-code-json" : "mdi-file-code-outline",
      label: extension ? extension.slice(0, 4).toUpperCase() : "CODE",
    };
  }
  return (
    fileTypeStyles[extension] || {
      color: "#607d8b",
      icon: "mdi-file-document-outline",
      label: extension ? extension.slice(0, 4).toUpperCase() : "FILE",
    }
  );
}
