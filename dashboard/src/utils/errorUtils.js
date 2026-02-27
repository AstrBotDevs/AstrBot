const INVALID_ERROR_STRINGS = new Set(["[object Object]", "undefined", "null"]);

export const resolveErrorMessage = (err, fallbackMessage = "") => {
  const fromResponse = err?.response?.data?.message;
  const fromError = err?.message;
  const raw = err != null ? String(err) : "";
  const fromString = INVALID_ERROR_STRINGS.has(raw) ? "" : raw;

  return fromResponse || fromError || fromString || fallbackMessage;
};
