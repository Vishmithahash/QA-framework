import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/shared/ui/Button/Button';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';
import './NotFoundPage.css';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="not-found-page">
      <EmptyState
        title="404 - Page Not Found"
        message="The page or route you requested does not exist in the QA framework."
        icon="🔍"
        action={
          <Link to="/">
            <Button variant="primary">Return to Overview</Button>
          </Link>
        }
      />
    </div>
  );
};
