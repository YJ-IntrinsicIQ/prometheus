import Link from "next/link";

export function BrandMark() {
  return (
    <Link href="/" className="inline-flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-surface text-sm font-semibold tracking-[0.18em] text-accent uppercase">
        IQ
      </div>
      <div>
        <p className="text-[0.7rem] uppercase tracking-[0.24em] text-muted">
          IntrinsicIQ
        </p>
        <p className="font-serif text-lg text-foreground">Ask IntrinsicIQ</p>
      </div>
    </Link>
  );
}
