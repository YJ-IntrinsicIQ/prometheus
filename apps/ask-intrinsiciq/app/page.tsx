import { AppFrame } from "@/src/components/layout/app-frame";
import { BrandMark } from "@/src/components/brand-mark";
import { CompanySearch } from "@/src/components/company-search";
import { landingView } from "@/src/data/landing-view";
import { getLandingCompanies } from "@/src/lib/ask-intrinsiciq";
import { COMPANIES } from "@/src/lib/story/companies";

export default async function HomePage() {
  // One selection flow: the companies the Cockpit supports, with availability from company discovery.
  const companies = (await getLandingCompanies()).filter((c) => c.slug in COMPANIES).map((c) => ({ ...c, name: COMPANIES[c.slug].name }));

  return (
    <AppFrame>
      <section className="editorial-card mx-auto max-w-5xl rounded-[32px] px-6 py-10 md:px-10 md:py-12">
        <BrandMark />
        <div className="mt-16 grid items-center gap-12 lg:min-h-[32rem] lg:grid-cols-[1.15fr_0.85fr]">
          <div className="max-w-3xl">
            <p className="text-xs uppercase tracking-[0.3em] text-muted">
              {landingView.experience}
            </p>
            <h1 className="mt-5 font-serif text-5xl leading-tight text-foreground md:text-7xl">
              {landingView.brand}
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-muted md:text-xl">
              {landingView.tagline}
            </p>
          </div>
          <CompanySearch
            searchLabel={landingView.searchLabel}
            helperText={landingView.helperText}
            companies={companies}
          />
        </div>
      </section>
    </AppFrame>
  );
}
