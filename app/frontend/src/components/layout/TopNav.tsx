import { NavLink } from "react-router-dom";

import { useAuth } from "../../lib/useAuth";
import { useTour } from "../tour/TourProvider";

export function TopNav() {
  const { logout } = useAuth();
  const { start } = useTour();
  return (
    <header className="text-sm">
      <div className="flex justify-end gap-4 px-4 pt-4">
        <button
          type="button"
          onClick={start}
          className="text-xs italic text-ink-faint transition-colors hover:text-ink"
        >
          tour
        </button>
        <button
          type="button"
          onClick={() => logout()}
          className="text-xs italic text-ink-faint transition-colors hover:text-ink"
        >
          logout
        </button>
      </div>
      <nav className="mx-auto mt-2 flex max-w-5xl justify-center gap-6 px-8 pb-2 text-ink-mute">
        <TabLink to="/" end dataTour="nav-home">
          Home
        </TabLink>
        <TabLink to="/digging" dataTour="nav-digging">
          Digging
        </TabLink>
        <TabLink to="/artists" dataTour="nav-artists">
          Artists
        </TabLink>
      </nav>
    </header>
  );
}

function TabLink({
  to,
  end,
  children,
  dataTour,
}: {
  to: string;
  end?: boolean;
  children: React.ReactNode;
  dataTour?: string;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      data-tour={dataTour}
      className={({ isActive }) =>
        isActive ? "text-ink" : "text-ink-mute hover:text-ink"
      }
    >
      {children}
    </NavLink>
  );
}
