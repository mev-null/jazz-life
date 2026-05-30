import { Outlet } from "react-router-dom";

import { AuthGate } from "../AuthGate";
import { ToastProvider } from "../ToastProvider";
import { useBreakpoint } from "../../hooks/useBreakpoint";
import { MOBILE_UI_ENABLED } from "../../lib/featureFlags";
import { BottomTabBar } from "./BottomTabBar";
import { TopNav } from "./TopNav";

export function AppLayout() {
  const { isMobile } = useBreakpoint();
  const mobile = MOBILE_UI_ENABLED && isMobile;
  return (
    <AuthGate>
      <ToastProvider>
        <div className="flex min-h-screen flex-col">
          {!mobile && <TopNav />}
          <main
            className={
              mobile
                ? "flex-1 px-5 pt-6 pb-24"
                : "mx-auto w-full max-w-5xl flex-1 px-8 py-10"
            }
          >
            <Outlet />
          </main>
          {mobile && <BottomTabBar />}
        </div>
      </ToastProvider>
    </AuthGate>
  );
}
