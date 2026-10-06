import { redirect } from 'next/navigation'

/**
 * Permanent redirect shim: the "India Workation & Long Weekend Finder" was
 * renamed to "Leave Planner" in the UI/docs (the underlying feature/data is
 * unchanged). This keeps `/workation` working for anyone who already
 * bookmarked or shared it rather than 404ing.
 */
export default function WorkationRedirectPage() {
  redirect('/leave-planner')
}
