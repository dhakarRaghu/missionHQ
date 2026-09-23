import { redirect } from "next/navigation";

export default function InboxPage() {
  // The Inbox is part of Home now. Kept as a redirect so an old bookmark, a
  // Telegram message or a note that links here still lands somewhere.
  redirect("/home");
}
