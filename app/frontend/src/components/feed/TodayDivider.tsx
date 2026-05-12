/**
 * "today" のラベル付き水平罫。Feed のタイムラインで upcoming と past を区切る。
 * 区切り線・ラベル共に元は ink-faint / bg-ink/15 で薄すぎたため、両方とも 1 段
 * 濃く (ink-mute / bg-ink/35) して視認性を上げてある。
 */
export function TodayDivider() {
  return (
    <div className="my-3 flex items-center gap-3 text-xs italic text-ink-mute">
      <div className="h-px flex-1 bg-ink/35" />
      <span>today</span>
      <div className="h-px flex-1 bg-ink/35" />
    </div>
  );
}
