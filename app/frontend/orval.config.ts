import { defineConfig } from "orval";

// jazz-life の OpenAPI spec から TypeScript 型 + React Query hooks を生成する。
// spec は backend が所有する `app/backend/openapi.json` を読む。backend 未起動でも
// make gen / CI で型生成が可能。spec を更新するには `make spec` で backend の
// export スクリプトを呼ぶ。
// 生成先: src/api/generated/<tag>/<tag>.ts （tags-split）と src/api/generated/model/*.ts。
export default defineConfig({
  jazzlife: {
    input: {
      target: "../backend/openapi.json",
    },
    output: {
      mode: "tags-split",
      target: "src/api/generated",
      schemas: "src/api/generated/model",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      prettier: false,
      override: {
        mutator: {
          path: "./src/api/mutator.ts",
          name: "customFetch",
        },
        query: {
          useQuery: true,
          useMutation: true,
        },
      },
    },
  },
});
