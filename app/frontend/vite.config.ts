import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Override the hostnames the dev server accepts via env.
// Default: local + Codespaces. Pass a CSV when trying the dev server on Railway or
// reaching it from another environment, e.g. through a Cloudflare Tunnel.
export default defineConfig(({ mode }) => {
  // Second arg "." resolves against cwd; third arg "" lifts the VITE_ prefix filter
  // (loadEnv normally loads only VITE_-prefixed vars; an empty string allows all of them).
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
