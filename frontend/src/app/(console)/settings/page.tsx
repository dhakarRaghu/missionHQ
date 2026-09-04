import { SettingsView } from "@/components/features/settings/settings-view";
import { PageHeader } from "@/components/page-header";

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings"
        description="Where each part of Mission HQ is configured. Every row opens the page that owns that setting."
      />
      <SettingsView />
    </>
  );
}
