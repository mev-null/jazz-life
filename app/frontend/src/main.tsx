import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";

import { router } from "./App";
import { UnauthorizedError } from "./api/mutator";
import "./index.css";

// API 呼び出しが 401 を返したら ["auth", "me"] を null に倒し、useAuth → AuthGate
// 経由で `/login` に遷移させる。これにより画面表示後にセッションが切れたケースでも
// 自動的にログイン画面へ戻れる。
let queryClient: QueryClient;
const handleQueryError = (error: unknown) => {
  if (error instanceof UnauthorizedError) {
    queryClient.setQueryData(["auth", "me"], null);
  }
};

queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handleQueryError }),
  mutationCache: new MutationCache({ onError: handleQueryError }),
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
