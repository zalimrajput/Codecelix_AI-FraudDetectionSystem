import React from 'react';
import { PageHeader } from '../components/common/PageHeader';

export const RulesPage: React.FC = () => {
  // The Rules Engine page has been removed: rule changes are not stored on
  // the user's workstation anymore. They affect the live backend scoring,
  // so this feature is disabled in this deployment.
  return <div className="space-y-6">
    <PageHeader
      title="Rules Engine"
      description="Rule changes affect the live fraud scoring backend. This feature is disabled in this deployment."
    />
    <p className="text-sm text-slate-400">
      The Rules Engine has been removed from this deployment. Do not change
      scoring rules here — they directly affect the backend fraud scoring.
    </p>
  </div>;
};
