import { redirect } from "next/navigation";

export default function Home() {
  // Attention flows to gates: approvals are the landing page.
  redirect("/inbox");
}
