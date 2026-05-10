import { Link, Outlet, createBrowserRouter } from "react-router-dom";

import { ArtistsPage } from "./pages/ArtistsPage";
import { FeedPage } from "./pages/FeedPage";
import { HomePage } from "./pages/HomePage";

function Layout() {
  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <header className="border-b border-neutral-200 bg-white">
        <nav className="mx-auto flex max-w-5xl gap-4 px-4 py-3">
          <Link to="/" className="font-semibold">
            jazz-life
          </Link>
          <span className="text-neutral-300">|</span>
          <Link to="/">Home</Link>
          <Link to="/feed">Feed</Link>
          <Link to="/artists">Artists</Link>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

export const router = createBrowserRouter([
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
