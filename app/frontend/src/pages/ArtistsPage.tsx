import { useQuery } from "@tanstack/react-query";

import { getArtists } from "../api/client";

export function ArtistsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["artists"],
    queryFn: getArtists,
  });

  return (
    <section>
      <h1 className="text-2xl font-semibold">Artists — アーティスト管理</h1>
      <p className="mt-2 text-sm text-neutral-500">
        Phase A 雛形：一覧・追加・エイリアス管理 UI は A-13/A-14 で実装。
      </p>
      <div className="mt-4">
        {isLoading && <span>loading…</span>}
        {isError && <span>load error</span>}
        {data && (
          <ul className="list-disc pl-6">
            {data.items.map((a) => (
              <li key={a.spotify_id}>{a.name}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
