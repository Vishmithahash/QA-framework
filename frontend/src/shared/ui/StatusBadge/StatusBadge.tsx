import React from 'react';
import './StatusBadge.css';

export type StatusBadgeVariant = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export interface StatusBadgeProps {
  status: string | null | undefined;
  variant?: StatusBadgeVariant;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, variant, className = '' }) => {
  const displayText =
    status !== null && status !== undefined && status.trim() !== '' ? status : 'Unknown';

  // Unknown values remain visible with neutral styling by default
  const resolvedVariant: StatusBadgeVariant = variant ?? 'neutral';

  return (
    <span className={`status-badge status-badge-${resolvedVariant} ${className}`}>
      {displayText}
    </span>
  );
};
