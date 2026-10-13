import React, { type ReactNode } from 'react';
import './PageHeader.css';

export interface PageHeaderProps {
  title: string;
  description?: string;
  badge?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  badge,
  actions,
  className = '',
}) => {
  return (
    <header className={`page-header ${className}`}>
      <div className="page-header-row">
        <div className="page-header-titles">
          <h1 className="page-header-title">{title}</h1>
          {badge && <div className="page-header-badge">{badge}</div>}
        </div>
        {actions && <div className="page-header-actions">{actions}</div>}
      </div>
      {description && <p className="page-header-description">{description}</p>}
    </header>
  );
};
