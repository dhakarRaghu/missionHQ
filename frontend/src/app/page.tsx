import { redirect } from "next/navigation";

export default function Root() {
  // Home answers "what is my system doing" in one screen; the Inbox is one
  // click away from it and is called out whenever a decision is waiting.
  redirect("/home");
}
