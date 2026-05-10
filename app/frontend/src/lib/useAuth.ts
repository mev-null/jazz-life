import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { getMe, login, logout } from "../api/auth";

/**
 * 認証状態を React Query で管理するフック。
 *
 * `["auth", "me"]` キーを真実の出所とし、login / logout はその cache を invalidate する。
 * 認証の判定は常にサーバが下す（mock では localStorage が代理）ため、フロントが
 * 「ログイン済みフラグ」を独自に持つことはしない。
 */
export function useAuth() {
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["auth", "me"] }),
  });

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      // logout 直後に getMe を再取得すると 401 で null を返すが、
      // mock ではそれが通信往復しないので即時 null をセットする。
      queryClient.setQueryData(["auth", "me"], null);
    },
  });

  return {
    user: meQuery.data ?? null,
    isAuthenticated: !!meQuery.data,
    isLoading: meQuery.isLoading,
    login: () => loginMutation.mutateAsync(),
    logout: () => logoutMutation.mutate(),
  };
}
