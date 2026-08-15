import '@testing-library/jest-dom'

// jsdom doesn't implement scrollIntoView — used by ChatPanel (and anything
// else that autoscrolls a message list into view) — stub it globally so
// tests don't have to special-case it per-file.
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
