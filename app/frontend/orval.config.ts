import { defineConfig } from "orval";

// Generate TypeScript types + React Query hooks from the jazz-life OpenAPI spec.
// Reads the backend-owned `app/backend/openapi.json`, so `make gen` / CI can generate
// types without a running backend. To refresh the spec, run `make spec`, which calls
// the backend's export script.
// Output: src/api/generated/<tag>/<tag>.ts (tags-split) and src/api/generated/model/*.ts.
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
