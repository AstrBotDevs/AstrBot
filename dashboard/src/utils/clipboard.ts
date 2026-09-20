interface CopyToClipboardOptions {
  container?: HTMLElement | null;
}

export async function copyToClipboard(
  text: string,
  options: CopyToClipboardOptions = {},
): Promise<boolean> {
  const container = options.container;
  const debugInfo = {
    length: text?.length ?? 0,
    trimmedLength: text?.trim().length ?? 0,
    isSecureContext: typeof window !== "undefined" ? window.isSecureContext : false,
    hasClipboardApi:
      typeof navigator !== "undefined" && !!navigator.clipboard?.writeText,
    containerTag: container?.tagName ?? null,
    containerInBody:
      typeof document !== "undefined" && !!container && document.body.contains(container),
  };

  if (!text) {
    console.debug("[clipboard] empty text payload", debugInfo);
    return false;
  }

  console.debug("[clipboard] copy request", debugInfo);

  if (typeof navigator !== "undefined" && navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      console.info("[clipboard] copied via Clipboard API", debugInfo);
      return true;
    } catch (err) {
      console.warn("[clipboard] Clipboard API failed, falling back:", err, debugInfo);
    }
  }

  const fallbackOk = fallbackCopy(text, container);
  if (fallbackOk) {
    console.info("[clipboard] fallback succeeded via document.execCommand('copy')", debugInfo);
  } else {
    console.warn("[clipboard] fallback failed via document.execCommand('copy')", debugInfo);
  }
  return fallbackOk;
}

function fallbackCopy(text: string, container?: HTMLElement | null): boolean {
  if (typeof document === "undefined" || !document.body) return false;

  const mountTarget =
    container && document.body.contains(container) ? container : document.body;
  const textArea = document.createElement("textarea");
  const activeElement =
    document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const selection = document.getSelection();
  const selectedRanges = selection
    ? Array.from({ length: selection.rangeCount }, (_, index) =>
        selection.getRangeAt(index).cloneRange(),
      )
    : [];

  textArea.value = text;
  textArea.readOnly = true;
  Object.assign(textArea.style, {
    position: "fixed",
    left: "-9999px",
    top: "0",
    opacity: "0",
    pointerEvents: "none",
  });

  mountTarget.appendChild(textArea);
  textArea.focus();
  textArea.select();
  textArea.setSelectionRange(0, text.length);

  try {
    return document.execCommand("copy");
  } catch (err) {
    console.error("Fallback copy failed:", err);
    return false;
  } finally {
    if (textArea.parentNode) {
      textArea.parentNode.removeChild(textArea);
    }
    if (selection) {
      selection.removeAllRanges();
      selectedRanges.forEach((range) => selection.addRange(range));
    }
    activeElement?.focus?.();
  }
}
