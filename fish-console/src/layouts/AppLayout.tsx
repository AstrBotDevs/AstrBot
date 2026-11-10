import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { siteConfig } from "../config/site";
import { useAuth } from "../context/AuthContext";

type NavItem = {
  to?: string;
  href?: string;
  label: string;
  external?: boolean;
};

type NavSection = {
  caption: string;
  items: NavItem[];
};

const navSections: NavSection[] = [
  {
    caption: "大肥鱼",
    items: [
      { to: "/dashboard", label: "饭碗" },
      { to: "/plans", label: "电饭煲" },
      { to: "/bot", label: "接鱼回家" },
    ],
  },
  {
    caption: "小账本",
    items: [
      { to: "/orders", label: "添饭记录" },
      { to: "/usage", label: "干饭记录" },
    ],
  },
  {
    caption: "鱼片",
    items: [
      { to: "/profile", label: "鱼片小窝" },
      { to: "/tickets", label: "找鱼咖聊聊" },
    ],
  },
];

const pageTitles: Record<string, string> = {
  "/dashboard": "大肥鱼的饭碗",
  "/plans": "大肥鱼电饭煲站",
  "/bot": "接鱼回家",
  "/usage": "干饭记录",
  "/orders": "添饭记录",
  "/profile": "鱼片小窝",
  "/tickets": "找鱼咖聊聊",
  "/admin/orders": "鱼咖收银台（管理员）",
};

function resolveTitle(pathname: string) {
  return pageTitles[pathname] ?? "鱼咖小店";
}

export function AppLayout() {
  const { email, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const title = resolveTitle(pathname);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">{siteConfig.brandName}</div>
        {isAdmin ? (
          <div>
            <div className="nav-caption">鱼咖</div>
            <nav className="nav-group" aria-label="鱼咖">
              <NavLink
                to="/admin/orders"
                className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
              >
                鱼咖收银台（管理员）
              </NavLink>
            </nav>
          </div>
        ) : null}
        {navSections.map((section) => (
          <div key={section.caption}>
            <div className="nav-caption">{section.caption}</div>
            <nav className="nav-group" aria-label={section.caption}>
              {section.items.map((item) =>
                item.to ? (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `nav-item${isActive ? " active" : ""}`
                    }
                  >
                    {item.label}
                  </NavLink>
                ) : null,
              )}
            </nav>
          </div>
        ))}
        {siteConfig.docsUrl ? (
          <a
            className="nav-item"
            href={siteConfig.docsUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            养鱼小抄
          </a>
        ) : null}
        <div className="version">{siteConfig.consoleVersion}</div>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1 className="page-title">{title}</h1>
          <div className="topbar-actions">
            <span className="user-chip">{email ?? "没登入"}</span>
            <button type="button" className="btn-text" onClick={handleLogout}>
              先溜了
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
