import { NavLink, Outlet, createBrowserRouter } from "react-router-dom";

import { AuthGate } from "./components/AuthGate";
import { useAuth } from "./lib/useAuth";
import { ArtistsPage } from "./pages/ArtistsPage";
import { FeedPage } from "./pages/FeedPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";

function Header() {
  const { logout } = useAuth();
  return (
    <header className="text-sm">
      <div className="flex justify-end px-4 pt-4">
        <button
          type="button"
          onClick={() => logout()}
          className="text-xs italic text-ink-faint transition-colors hover:text-ink"
        >
          logout
        </button>
      </div>
      <nav className="mx-auto mt-2 flex max-w-5xl justify-center gap-6 px-8 pb-2 text-ink-mute">
        <TabLink to="/" end>
          Home
        </TabLink>
        <TabLink to="/feed">Feed</TabLink>
        <TabLink to="/artists">Artists</TabLink>
      </nav>
    </header>
  );
}

function TabLink({
  to,
  end,
  children,
}: {
  to: string;
  end?: boolean;
  children: React.ReactNode;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        isActive ? "text-ink" : "text-ink-mute hover:text-ink"
      }
    >
      {children}
    </NavLink>
  );
}

function Layout() {
  return (
    <AuthGate>
      <div className="flex min-h-screen flex-col">
        <Header />
        <main className="mx-auto w-full max-w-5xl flex-1 px-8 py-10">
          <Outlet />
        </main>
      </div>
    </AuthGate>
  );
}

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "feed", element: <FeedPage /> },
      { path: "artists", element: <ArtistsPage /> },
    ],
  },
]);
