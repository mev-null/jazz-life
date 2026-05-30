import { NavLink } from "react-router-dom";

import { useAuth } from "../../lib/useAuth";

export function TopNav() {
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
        <TabLink to="/digging">Digging</TabLink>
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
