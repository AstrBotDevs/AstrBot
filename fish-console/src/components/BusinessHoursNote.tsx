import { siteConfig } from "../config/site";

type BusinessHoursNoteProps = {
  /** Compact single-block note for sidebar. */
  compact?: boolean;
};

export function BusinessHoursNote({ compact = false }: BusinessHoursNoteProps) {
  const { businessHours } = siteConfig;

  if (compact) {
    return (
      <div className="hours-note hours-note--compact" role="note" aria-label="营业时间">
        <p className="hours-note-title">{businessHours.title}</p>
        <p className="hours-note-line">
          <strong>{businessHours.hours}</strong>
          <span className="hours-note-sub">（{businessHours.hint}）</span>
        </p>
        <p className="hours-note-line muted">{businessHours.quotaNote}</p>
      </div>
    );
  }

  return (
    <aside className="hours-note hours-note--card" role="note" aria-label="营业时间">
      <p className="hours-note-title">{businessHours.title}</p>
      <p className="hours-note-hours">{businessHours.hours}</p>
      <p className="hours-note-hint">{businessHours.hint}</p>
      <p className="hours-note-quota">{businessHours.quotaNote}</p>
    </aside>
  );
}
