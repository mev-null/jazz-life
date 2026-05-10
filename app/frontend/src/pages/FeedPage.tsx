import { useQuery } from "@tanstack/react-query";

import { getConcerts, getReleases } from "../api/client";

export function FeedPage() {
  const releases = useQuery({ queryKey: ["releases"], queryFn: getReleases });
  const concerts = useQuery({ queryKey: ["concerts"], queryFn: getConcerts });

  return (
    <section>
      <h1 className="text-2xl font-semibold">Feed — 新譜・公演</h1>
      <p className="mt-2 text-sm text-neutral-500">
        Phase A 雛形：タブ切替・カード UI は A-16/A-17 で実装。
      </p>
      <div className="mt-4 grid grid-cols-2 gap-4">
        <div>
          <h2 className="font-medium">新譜</h2>
          <p>{releases.data ? `${releases.data.items.length} 件` : "—"}</p>
        </div>
        <div>
          <h2 className="font-medium">公演</h2>
          <p>{concerts.data ? `${concerts.data.items.length} 件` : "—"}</p>
        </div>
      </div>
    </section>
  );
}
