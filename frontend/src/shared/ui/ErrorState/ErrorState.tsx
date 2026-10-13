import React, { type ReactNode } from 'react';
import { Button } from '@/shared/ui/Button/Button';
import './ErrorState.css';

export interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  action?: ReactNode;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'An error occurred',
  message = 'Something unexpected happened while processing your request.',
  onRetry,
  action,
  className = '',
}) => {
  return (
    <div className={`error-state ${className}`} role="alert">
      <div className="error-state-icon" aria-hidden="true">
        ⚠️
      </div>
      <h3 className="error-state-title">{title}</h3>
      <p className="error-state-message">{message}</p>
      {(onRetry || action) && (
        <div className="error-state-action">
          {onRetry && (
            <Button variant="secondary" onClick={onRetry}>
              Try Again
            </Button>
          )}
          {action}
        </div>
      )}
    </div>
  );
};
