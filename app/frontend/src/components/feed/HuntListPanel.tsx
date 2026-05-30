import { useMemo } from "react";

import { formatShortDate } from "../../lib/dates";
import type { Artist, VinylRecord } from "../../types/api";
import { JacketArt } from "../records/JacketCard";

export type HuntSort = "artist" | "added";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

// アーティスト名の頭文字を A–Z レール用に正規化する。英字以外は "#" に寄せる。
function initialOf(name: string): string {
  const c = name.trim().charAt(0).toUpperCase();
  return c >= "A" && c <= "Z" ? c : "#";
}

/**
 * Hunt list の 1 行。Releases の `ReleaseRow` と同じ行ビジュアルに揃える
 * (左ガター + 64px ジャケット + title / artist / pressing_info + 右に日付)。
 * hunt list に既読概念は無いので未読 dot は出さない。
 */
function HuntRow({
  record,
  artistName,
  onClick,
}: {
  record: VinylRecord;
  artistName: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full cursor-pointer items-stretch gap-3 py-3 text-left text-sm transition-opacity hover:opacity-80"
    >
      <span className="w-2 shrink-0" />
      <div className="relative aspect-square w-16 shrink-0 overflow-hidden ring-1 ring-ink/10">
        <JacketArt record={record} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col justify-center">
        <div className="truncate font-medium">{record.title}</div>
        <div className="mt-0.5 truncate text-ink-mute">{artistName}</div>
        {record.pressing_info && (
          <div className="mt-0.5 truncate text-xs italic text-ink-faint">
            {record.pressing_info}
          </div>
        )}
      </div>
      <span className="shrink-0 self-center text-ink-mute tabular-nums">
        {formatShortDate(record.created_at)}
      </span>
    </button>
  );
}

type Props = {
  // backend で sort 済みの wanted レコード。frontend は並べ替えずグループ化だけ行う。
  records: VinylRecord[];
  artists: Artist[];
  sort: HuntSort;
  onSortChange: (sort: HuntSort) => void;
  onRecordClick: (record: VinylRecord) => void;
};

export function HuntListPanel({
  records,
  artists,
  sort,
  onSortChange,
  onRecordClick,
}: Props) {
  const nameById = useMemo(
    () => new Map(artists.map((a) => [a.spotify_id, a.name])),
    [artists],
  );
  const artistName = (id: string) => nameById.get(id) ?? "—";

  // artist モード: backend が name 昇順で返すので、連続する同一 artist を
  // グループ見出しにまとめるだけ。各 letter の先頭グループに anchor を張り、
  // A–Z レールのジャンプ先にする。
  const groups = useMemo(() => {
    if (sort !== "artist") return [];
    const out: { artistId: string; name: string; letter: string; records: VinylRecord[] }[] = [];
    for (const r of records) {
      const last = out[out.length - 1];
      if (last && last.artistId === r.artist_id) {
        last.records.push(r);
      } else {
        const name = artistName(r.artist_id);
        out.push({ artistId: r.artist_id, name, letter: initialOf(name), records: [r] });
      }
    }
    return out;
  }, [records, sort, nameById]);

  // letter -> 最初に出現するグループ index (anchor を張る対象)。
  const firstGroupByLetter = useMemo(() => {
    const map = new Map<string, number>();
    groups.forEach((g, i) => {
      if (!map.has(g.letter)) map.set(g.letter, i);
    });
    return map;
  }, [groups]);

  const railLetters = [...ALPHABET, "#"];
  const presentLetters = new Set(firstGroupByLetter.keys());

  function jumpTo(letter: string) {
    document
      .getElementById(`hunt-letter-${letter}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div>
      <h1 className="flex items-baseline gap-3 text-base">
        <span className="font-medium">On the hunt</span>
        <span className="text-ink-faint tabular-nums">{records.length}</span>
        <button
          type="button"
          onClick={() => onSortChange(sort === "artist" ? "added" : "artist")}
          className="ml-auto cursor-pointer text-xs italic text-ink-mute transition-colors hover:text-ink"
        >
          {sort === "artist" ? "by artist" : "by added"}
        </button>
      </h1>

      {records.length === 0 ? (
        <p className="mt-6 text-sm italic text-ink-mute">nothing on the hunt yet</p>
      ) : sort === "added" ? (
        <div className="mt-4 divide-y divide-ink-faint/30">
          {records.map((r) => (
            <HuntRow
              key={r.id}
              record={r}
              artistName={artistName(r.artist_id)}
              onClick={() => onRecordClick(r)}
            />
          ))}
        </div>
      ) : (
        <div className="mt-4 flex gap-2">
          <div className="min-w-0 flex-1">
            {groups.map((g, i) => (
              <section key={g.artistId}>
                <h2
                  id={
                    firstGroupByLetter.get(g.letter) === i
                      ? `hunt-letter-${g.letter}`
                      : undefined
                  }
                  className="scroll-mt-24 pt-4 text-xs italic uppercase tracking-wider text-ink-faint"
                >
                  {g.name}
                </h2>
                <div className="divide-y divide-ink-faint/30">
                  {g.records.map((r) => (
                    <HuntRow
                      key={r.id}
                      record={r}
                      artistName={g.name}
                      onClick={() => onRecordClick(r)}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
          {/* A–Z インデックスレール (旧 iOS Contacts 風)。artist モード時のみ。 */}
          <nav
            aria-label="alphabet index"
            className="sticky top-24 flex h-fit shrink-0 flex-col items-center gap-0.5 self-start py-1 text-[10px] leading-none tabular-nums"
          >
            {railLetters.map((letter) =>
              presentLetters.has(letter) ? (
                <button
                  key={letter}
                  type="button"
                  onClick={() => jumpTo(letter)}
                  className="cursor-pointer px-1 text-ink-mute transition-colors hover:text-ink"
                >
                  {letter}
                </button>
              ) : (
                <span key={letter} className="px-1 text-ink-faint/50">
                  {letter}
                </span>
              ),
            )}
          </nav>
        </div>
      )}
    </div>
  );
}
