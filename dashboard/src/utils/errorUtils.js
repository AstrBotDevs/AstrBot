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
    return err.trim() || fallbackMessage;
  }
  if (typeof err === "number" || typeof err === "boolean") {
    return String(err);
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
    const value = err.toString().trim();
    fromString = INVALID_ERROR_STRINGS.has(value) ? "" : value;
  }

  return fromResponse || fromError || fromString || fallbackMessage;
};
