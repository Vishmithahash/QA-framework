import React, { type ReactNode } from 'react';
import './EmptyState.css';

export interface EmptyStateProps {
  title: string;
  message: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  message,
  icon,
  action,
  className = '',
}) => {
  return (
    <div className={`empty-state ${className}`}>
      {icon ? (
        <div className="empty-state-icon">{icon}</div>
      ) : (
        <div className="empty-state-icon" aria-hidden="true">
          📂
        </div>
      )}
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-message">{message}</p>
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
};
