import { ToolsView } from "@/components/features/tools/tools-view";
import { PageHeader } from "@/components/page-header";

export default function ToolsPage() {
  return (
    <>
      <PageHeader
        title="Tools"
        description="Everything your agents can do, grouped by how far it reaches. A tool is granted in an agent's manifest, so this page reads the registry rather than switching anything on."
      />
      <ToolsView />
    </>
  );
}
