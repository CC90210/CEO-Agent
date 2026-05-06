/**
 * Root loading skeleton. Renders during route transitions (Next.js streams
 * this in while the next page's server components fetch). Replaces the
 * blank flash users would otherwise see.
 *
 * Intentionally minimal — looks like the page is "thinking" without
 * mocking any specific data shape. The chat-aurora animation already
 * suggests motion; the fading bars below give a layout placeholder.
 */

export default function Loading() {
  return (
    <div className="space-y-6 animate-fade-in" aria-busy="true" aria-live="polite">
      <div className="space-y-2">
        <div className="h-7 w-48 rounded-md bg-bg-elev animate-pulse-slow" />
        <div className="h-4 w-72 rounded-md bg-bg-elev/60 animate-pulse-slow" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-24 rounded-xl border border-bg-border bg-bg-elev/60 animate-pulse-slow"
          />
        ))}
      </div>
      <div className="h-72 rounded-xl border border-bg-border bg-bg-elev/40 animate-pulse-slow" />
      <div className="h-48 rounded-xl border border-bg-border bg-bg-elev/40 animate-pulse-slow" />
    </div>
  );
}
