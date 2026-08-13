import { cleanPublicList, prepareLensBulletForDisplay } from "@/src/lib/ask-intrinsiciq/presentation";
import type { ResearchAnswerCard } from "@/src/types";

type StructuredAnswerSectionsProps = {
  sections: NonNullable<ResearchAnswerCard["structuredSections"]>;
};

const SECTION_STYLES: Record<
  string,
  {
    eyebrow: string;
    symbol: string;
    accentClass: string;
    badgeClass: string;
  }
> = {
  "what he may like": {
    eyebrow: "Positive signal",
    symbol: "✓",
    accentClass:
      "border-[rgba(74,109,94,0.18)] bg-[rgba(74,109,94,0.06)]",
    badgeClass:
      "border-[rgba(74,109,94,0.24)] bg-[rgba(74,109,94,0.1)] text-accent",
  },
  "what he would question": {
    eyebrow: "Open question",
    symbol: "?",
    accentClass:
      "border-[rgba(168,131,63,0.22)] bg-[rgba(168,131,63,0.08)]",
    badgeClass:
      "border-[rgba(168,131,63,0.28)] bg-[rgba(168,131,63,0.12)] text-gold",
  },
  "what remains unproven": {
    eyebrow: "Evidence limit",
    symbol: "○",
    accentClass:
      "border-[rgba(100,116,139,0.22)] bg-[rgba(148,163,184,0.08)]",
    badgeClass:
      "border-[rgba(100,116,139,0.24)] bg-[rgba(148,163,184,0.14)] text-slate-600",
  },
};

export function StructuredAnswerSections({
  sections,
}: StructuredAnswerSectionsProps) {
  if (sections.length === 0) {
    return null;
  }

  const sharedSeen = new Set<string>();

  return (
    <section className="rounded-[26px] border border-border bg-[rgba(255,255,255,0.44)] p-5 shadow-[0_14px_34px_rgba(15,23,42,0.04)] md:p-6">
      <div data-testid="wide-section-investor-lens" />
      <div>
        <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
          Investor lens
        </p>
        <h2 className="mt-1 text-[1.3rem] font-semibold tracking-[-0.01em] text-foreground md:text-[1.45rem]">
          Buffett-style summary
        </h2>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {sections.map((section, index) => {
          const sectionKey = section.title.toLowerCase();
          const style = SECTION_STYLES[sectionKey] ?? {
            eyebrow: "Structured view",
            symbol: "•",
            accentClass: "border-border bg-surface",
            badgeClass: "border-border bg-white/70 text-foreground",
          };

          return (
            <article
              key={section.title}
              className={`rounded-[20px] border px-4 py-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)] ${style.accentClass} ${
                index === 2 && sections.length === 3 ? "md:col-span-2 xl:col-span-1" : ""
              }`}
            >
              <div className="flex items-start gap-3">
                <span
                  className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-[0.95rem] font-semibold ${style.badgeClass}`}
                >
                  {style.symbol}
                </span>
                <div className="min-w-0">
                  <p className="text-[0.7rem] uppercase tracking-[0.1em] text-muted">
                    {style.eyebrow}
                  </p>
                  <h3 className="mt-1 text-[1rem] font-semibold leading-6 text-foreground">
                    {section.title}
                  </h3>
                </div>
              </div>
              <ul className="mt-4 space-y-3">
                {cleanPublicList(section.points, { seen: sharedSeen, limit: 3 }).map((point) => {
                  const prepared = prepareLensBulletForDisplay(point);
                  const isTrimmed = prepared !== point.trim();

                  return (
                    <li key={`${section.title}-${point}`} className="text-[0.92rem] leading-6 text-muted">
                      <div className="flex items-start gap-2">
                        <span className="mt-[0.55rem] h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-55" />
                        <div className="min-w-0">
                          <p title={point}>{prepared}</p>
                          {isTrimmed ? (
                            <details className="mt-1">
                              <summary className="cursor-pointer text-[0.8rem] text-muted underline decoration-border underline-offset-4">
                                Show detail
                              </summary>
                              <p className="mt-1 text-[0.88rem] leading-6 text-muted">
                                {point}
                              </p>
                            </details>
                          ) : null}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </article>
          );
        })}
      </div>
    </section>
  );
}
