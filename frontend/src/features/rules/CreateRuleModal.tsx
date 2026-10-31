import React from 'react';

// Rules Engine removed from this deployment: creating a rule writes directly
// into the live backend fraud scoring. This component always shows the
// disabled notice instead of editing real rules.
export const CreateRuleModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/70">
      <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-200">
        <h2 className="text-base font-semibold text-slate-100">Rules Engine Disabled</h2>
        <p className="mt-2 text-xs leading-relaxed text-slate-400">
          Rule changes affect the live backend fraud scoring. This feature has
          been removed from this deployment, so rules can no longer be added or
          edited here.
        </p>
        <button
          type="button"
          onClick={onClose}
          className="mt-5 w-full rounded-lg border border-slate-800 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 active:bg-slate-700"
        >
          Close
        </button>
      </div>
    </div>
  );
};
