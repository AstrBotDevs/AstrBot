import type { ReactNode } from "react";

interface ThinkingNoteProps {
  seconds: number;
  children: ReactNode;
}

/** 大肥鱼的内心戏，仿 DeepSeek「已深度思考」折叠块。 */
export function ThinkingNote({ seconds, children }: ThinkingNoteProps) {
  return (
    <details className="think" open>
      <summary className="think-summary">已深度思考（用时 {seconds} 秒）</summary>
      <div className="think-body">{children}</div>
    </details>
  );
}
