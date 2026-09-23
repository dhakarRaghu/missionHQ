import { redirect } from "next/navigation";

export default function FeedPage() {
  // The live feed is a tab on Runs now; same reason as /inbox -> /home.
  redirect("/runs?tab=feed");
}
