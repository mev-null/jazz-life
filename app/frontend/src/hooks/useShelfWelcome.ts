import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { getVinylRecords } from "../api/client";
import { useToast } from "../components/ToastProvider";

/** 1 → "1st", 2 → "2nd", 23 → "23rd", 11 → "11th"。英語の序数。 */
function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

/**
 * レコードが `owned` になった瞬間 (新規 owned 作成 / wanted→owned 遷移、ADR-015
 * §2.2 と同一面) に「棚入れ」を祝うトーストを画面上部に出す (ADR-017)。
 *
 * 思想: 実際に所有するという体験はユーザーにとって大きな意味を持つ。status
 * フラグの反転で即閉じるのではなく、コレクションへの迎え入れを静かに祝う。
 *
 * owned 総数は `["records"]` invalidate が非同期で確定するのを待たず、ここで
 * `status=owned` の total を fresh fetch して権威的に取得する。取得できない時は
 * 枚数を伏せ、誤った件数 (0th 等) は絶対に出さない。
 */
export function useShelfWelcome() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  return useCallback(async () => {
    let line = "Welcome to the collection.";
    try {
      const res = await queryClient.fetchQuery({
        queryKey: ["records", "owned-total"],
        queryFn: () => getVinylRecords(1, 0, "owned"),
        staleTime: 0,
      });
      if (typeof res.total === "number" && res.total > 0) {
        line = `Welcome to the collection — your ${ordinal(res.total)} record.`;
      }
    } catch {
      // 件数取得に失敗しても祝福自体は出す (枚数なしコピーのまま)。
    }
    showToast(line, { position: "top" });
  }, [showToast, queryClient]);
}
