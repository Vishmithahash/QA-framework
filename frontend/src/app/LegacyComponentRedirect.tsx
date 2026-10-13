import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';

export interface LegacyComponentRedirectProps {
  target: string;
}

export const LegacyComponentRedirect: React.FC<LegacyComponentRedirectProps> = ({ target }) => {
  const location = useLocation();
  const subpath = location.pathname.replace(/^\/components\/[^/]+/, '');
  return <Navigate to={`/testing/${target}${subpath}${location.search}`} replace />;
};

export default LegacyComponentRedirect;
