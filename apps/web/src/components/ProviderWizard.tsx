import React from "react";

import { ProviderManagementWorkspace } from "./providers/ProviderManagementWorkspace";

interface ProviderWizardProps {
  onClose: () => void;
  onSaved: () => void;
}

export function ProviderWizard({ onClose, onSaved }: ProviderWizardProps) {
  return (
    <ProviderManagementWorkspace
      onClose={onClose}
      onProfilesChanged={onSaved}
    />
  );
}
