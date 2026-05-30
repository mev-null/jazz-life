import { createBrowserRouter } from "react-router-dom";

import { Navigate } from "react-router-dom";

import { AppLayout } from "./components/layout/AppLayout";
import { ArtistsPage } from "./pages/ArtistsPage";
import { DiggingPage } from "./pages/DiggingPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "digging", element: <DiggingPage /> },
      // タブを URL に反映する (/digging/hunt | listen | releases)。
      // 無印 /digging は hunt タブにフォールバック (DiggingPage 側で正規化)。
      { path: "digging/:tab", element: <DiggingPage /> },
      // 旧 /feed パスからの後方互換リダイレクト (ADR-013 で Digging に改名)。
      { path: "feed", element: <Navigate to="/digging" replace /> },
      { path: "artists", element: <ArtistsPage /> },
    ],
  },
]);
