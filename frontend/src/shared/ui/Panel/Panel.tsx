import React, { type ReactNode } from 'react';
import './Panel.css';

export interface PanelProps {
  title?: ReactNode;
  headerAction?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  elevated?: boolean;
  className?: string;
}

export const Panel: React.FC<PanelProps> = ({
  title,
  headerAction,
  footer,
  children,
  elevated = false,
  className = '',
}) => {
  const classes = ['panel', elevated ? 'panel-elevated' : '', className].filter(Boolean).join(' ');

  return (
    <div className={classes}>
      {(title || headerAction) && (
        <div className="panel-header">
          {title && (typeof title === 'string' ? <h3 className="panel-title">{title}</h3> : title)}
          {headerAction && <div className="panel-header-action">{headerAction}</div>}
        </div>
      )}
      <div className="panel-body">{children}</div>
      {footer && <div className="panel-footer">{footer}</div>}
    </div>
  );
};
