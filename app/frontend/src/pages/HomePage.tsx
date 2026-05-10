import { useQuery } from "@tanstack/react-query";

import { getVinylRecords } from "../api/client";

export function HomePage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["records"],
    queryFn: getVinylRecords,
  });

  return (
    <section>
      <h1 className="text-2xl font-semibold">Home — レコードコレクション</h1>
      <p className="mt-2 text-sm text-neutral-500">
        Phase A 雛形：マトリクス UI は A-5 以降で実装。
      </p>
      <div className="mt-4">
        {isLoading && <span>loading…</span>}
        {isError && <span>load error</span>}
        {data && <span>所有レコード: {data.items.length} 枚</span>}
      </div>
    </section>
  );
}
