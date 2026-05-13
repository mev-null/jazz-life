import { NavLink } from "react-router-dom";

export function BottomTabBar() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-rule bg-paper pb-[env(safe-area-inset-bottom)]">
      <ul className="flex h-14 items-stretch justify-around">
        <BottomTabItem to="/" end label="Home" />
        <BottomTabItem to="/feed" label="Feed" />
        <BottomTabItem to="/artists" label="Artists" />
      </ul>
    </nav>
  );
}

function BottomTabItem({
  to,
  end,
  label,
}: {
  to: string;
  end?: boolean;
  label: string;
}) {
  return (
    <li className="flex flex-1">
      <NavLink
        to={to}
        end={end}
        className={({ isActive }) =>
          `flex flex-1 items-center justify-center text-xs uppercase tracking-wider transition-colors ${
            isActive ? "text-ink" : "text-ink-mute"
          }`
        }
      >
        {label}
      </NavLink>
    </li>
  );
}
