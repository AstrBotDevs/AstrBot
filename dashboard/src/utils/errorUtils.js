const INVALID_ERROR_STRINGS = new Set(["[object Object]", "undefined", "null", ""]);

const pickResponseMessage = (responseData) => {
  if (typeof responseData === "string") {
    return responseData.trim();
  }
  if (!responseData || typeof responseData !== "object") {
    return "";
  }

  const keys = ["message", "error", "detail", "details", "msg"];
  for (const key of keys) {
    const value = responseData[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
};

export const resolveErrorMessage = (err, fallbackMessage = "") => {
  if (typeof err === "string") {
    const value = err.trim();
    return INVALID_ERROR_STRINGS.has(value) ? fallbackMessage : value;
  }
  if (typeof err === "number" || typeof err === "boolean") {
    return fallbackMessage;
  }

  const fromResponse =
    pickResponseMessage(err?.response?.data) ||
    (typeof err?.response?.statusText === "string"
      ? err.response.statusText.trim()
      : "");
  const fromError =
    typeof err?.message === "string" ? err.message.trim() : "";

  let fromString = "";
  if (typeof err?.toString === "function") {
    try {
      const raw = err.toString();
      const value = typeof raw === "string" ? raw.trim() : "";
      fromString = INVALID_ERROR_STRINGS.has(value) ? "" : value;
    } catch {
      fromString = "";
    }
  }

  return fromResponse || fromError || fromString || fallbackMessage;
};
