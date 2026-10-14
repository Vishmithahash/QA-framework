import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useProjectContext } from '@/shared/hooks/useProjectContext';
import './AppShell.css';

export interface AppShellProps {
  children?: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const { activeProject, clearActiveProject } = useProjectContext();

  return (
    <div className="app-shell">
      {/* Skip to Content accessible link */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* Sidebar */}
      <aside className="app-sidebar" aria-label="Main Navigation">
        <div className="sidebar-header">
          <div className="sidebar-logo" aria-hidden="true">
            QA
          </div>
          <div>
            <div className="sidebar-title">Agentic AI QA</div>
            <div className="sidebar-subtitle">Software Framework</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div>
            <div className="nav-section-title">Workspace</div>
            <ul className="nav-list">
              <li>
                <NavLink
                  to="/"
                  end
                  className={({ isActive }) => `nav-item-link ${isActive ? 'active' : ''}`}
                >
                  <span className="nav-icon" aria-hidden="true">
                    📊
                  </span>
                  <span>Overview</span>
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/projects"
                  className={({ isActive }) => `nav-item-link ${isActive ? 'active' : ''}`}
                >
                  <span className="nav-icon" aria-hidden="true">
                    📁
                  </span>
                  <span>Projects</span>
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/testing"
                  className={({ isActive }) => `nav-item-link ${isActive ? 'active' : ''}`}
                >
                  <span className="nav-icon" aria-hidden="true">
                    🧪
                  </span>
                  <span>Testing</span>
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/test-runs"
                  className={({ isActive }) => `nav-item-link ${isActive ? 'active' : ''}`}
                >
                  <span className="nav-icon" aria-hidden="true">
                    ⚡
                  </span>
                  <span>Test Runs</span>
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/reports"
                  className={({ isActive }) => `nav-item-link ${isActive ? 'active' : ''}`}
                >
                  <span className="nav-icon" aria-hidden="true">
                    📈
                  </span>
                  <span>Reports</span>
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/settings"
                  className={({ isActive }) => `nav-item-link ${isActive ? 'active' : ''}`}
                >
                  <span className="nav-icon" aria-hidden="true">
                    ⚙️
                  </span>
                  <span>Settings</span>
                </NavLink>
              </li>
            </ul>
          </div>
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="app-main-wrapper">
        <header className="app-header">
          <div className="header-left">
            {/* Project Context Area */}
            <div className="project-context-box" aria-label="Active Project Context">
              <span className="project-context-label">Project:</span>
              {activeProject ? (
                <>
                  <span className="project-context-value">{activeProject.name}</span>
                  <button
                    type="button"
                    onClick={clearActiveProject}
                    aria-label="Clear active project"
                    style={{
                      border: 'none',
                      background: 'none',
                      cursor: 'pointer',
                      fontSize: '12px',
                      color: 'var(--color-text-muted)',
                      padding: '0 2px',
                    }}
                  >
                    ✕
                  </button>
                </>
              ) : (
                <span className="project-context-value empty">No project selected.</span>
              )}
            </div>
          </div>

          <div className="header-right">
            <div className="system-status-indicator">
              <span className="system-status-dot" aria-hidden="true" />
              <span>Frontend Initialized</span>
            </div>
          </div>
        </header>

        <main id="main-content" className="app-main-content" tabIndex={-1}>
          {children ?? <Outlet />}
        </main>
      </div>
    </div>
  );
};

export default AppShell;
