/**
 * "today" のラベル付き水平罫。Feed のタイムラインで upcoming と past を区切る。
 */
export function TodayDivider() {
  return (
    <div className="my-3 flex items-center gap-3 text-xs italic text-ink-faint">
      <div className="h-px flex-1 bg-ink/15" />
      <span>today</span>
      <div className="h-px flex-1 bg-ink/15" />
    </div>
  );
}
