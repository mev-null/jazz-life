import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// dev server で受け入れるホスト名を env から差し替える。
// 既定: ローカル + Codespaces。Railway 上で dev server を試したい場合や
// 別環境で Cloudflare Tunnel 経由などで叩きたい場合に CSV で渡す。
export default defineConfig(({ mode }) => {
  // 第二引数 "." で cwd 解決、第三引数 "" で VITE_ prefix の制限を外す
  // (loadEnv は通常 VITE_ prefix のみ読み込むため、空文字で全 env を許可)。
  const env = loadEnv(mode, ".", "");
  const allowedHostsFromEnv = (env.VITE_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((s: string) => s.trim())
    .filter((s: string) => s.length > 0);

  const allowedHosts =
    allowedHostsFromEnv.length > 0
      ? allowedHostsFromEnv
      : [".app.github.dev", "localhost", "127.0.0.1"];

  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      allowedHosts,
    },
  };
});
