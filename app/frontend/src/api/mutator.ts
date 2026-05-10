// orval `httpClient: fetch` モード用カスタム mutator。
// 生成された fetcher (records.ts / artists.ts 等) はすべてこの関数を経由する。
//
// 呼び出し側のシグネチャ (orval@8 fetch mode):
//   customFetch<T>(url: string, options: RequestInit): Promise<T>
//
// orval が期待する戻り値の形:
//   { data: <Body>, status: <number>, headers: Headers }

import { API_BASE } from "../lib/env";

export const customFetch = async <T>(
  url: string,
  options: RequestInit,
): Promise<T> => {
  const res = await fetch(`${API_BASE}${url}`, options);

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      `API ${options.method ?? "GET"} ${url} failed: ${res.status}${
        detail ? ` — ${detail}` : ""
      }`,
    );
  }

  const data = res.status === 204 ? undefined : await res.json();

  return {
    status: res.status,
    data,
    headers: res.headers,
  } as T;
};
