import { Suspense } from "react";

import { CoursesView } from "@/components/features/courses/courses-view";

// CoursesView reads ?course=&phase= (a link from Home opens one phase), and a
// component that reads search params must sit under Suspense to prerender.
export default function CoursesPage() {
  return (
    <Suspense>
      <CoursesView />
    </Suspense>
  );
}
