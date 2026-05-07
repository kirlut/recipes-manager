import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    function onClickOutside() {
      setMenuOpen(false);
    }
    if (menuOpen) {
      window.addEventListener("click", onClickOutside);
      return () => window.removeEventListener("click", onClickOutside);
    }
  }, [menuOpen]);

  function handleLogout() {
    logout();
    setMenuOpen(false);
    navigate("/login");
  }

  return (
    <div className="min-h-screen flex flex-col bg-base-100">
      <header className="navbar bg-base-200 border-b border-base-300 px-2">
        <button
          type="button"
          aria-label="Open menu"
          className="btn btn-ghost btn-square md:hidden"
          onClick={() => setDrawerOpen(true)}
        >
          <span aria-hidden="true">☰</span>
        </button>
        <div className="flex-1 px-2">
          <Link
            to="/products"
            aria-label="Home"
            className="btn btn-ghost text-xl normal-case"
          >
            recipes-manager
          </Link>
        </div>
        {user && (
          <div className="relative">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((v) => !v);
              }}
            >
              {user.username}
            </button>
            {menuOpen && (
              <ul
                role="menu"
                className="absolute right-0 mt-1 menu menu-sm bg-base-100 rounded-box border border-base-300 shadow z-50 w-40 p-2"
              >
                <li>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={handleLogout}
                  >
                    Logout
                  </button>
                </li>
              </ul>
            )}
          </div>
        )}
      </header>

      <div className="flex flex-1">
        {drawerOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/40 md:hidden"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
        )}

        <nav
          aria-label="Primary"
          className={
            (drawerOpen
              ? "fixed inset-y-0 left-0 z-40 w-64 "
              : "hidden ") +
            "md:relative md:block md:inset-auto md:w-60 bg-base-200 border-r border-base-300 p-4"
          }
        >
          {drawerOpen && (
            <button
              type="button"
              aria-label="Close menu"
              className="btn btn-ghost btn-sm mb-2 md:hidden"
              onClick={() => setDrawerOpen(false)}
            >
              ✕
            </button>
          )}
          <ul className="menu p-0 gap-1">
            <li>
              <NavLink
                to="/products"
                onClick={() => setDrawerOpen(false)}
                className={({ isActive }) =>
                  isActive ? "active font-semibold" : ""
                }
              >
                My Products
              </NavLink>
            </li>
            <li>
              <NavLink
                to="/recipes"
                onClick={() => setDrawerOpen(false)}
                className={({ isActive }) =>
                  isActive ? "active font-semibold" : ""
                }
              >
                My Recipes
              </NavLink>
            </li>
            <li>
              <NavLink
                to="/shopping-list"
                onClick={() => setDrawerOpen(false)}
                className={({ isActive }) =>
                  isActive ? "active font-semibold" : ""
                }
              >
                Shopping List
              </NavLink>
            </li>
          </ul>
        </nav>

        <main className="flex-1 p-4 min-w-0">{children}</main>
      </div>
    </div>
  );
}
