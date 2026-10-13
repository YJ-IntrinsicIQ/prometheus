import Link from "next/link";
import { companyRoute } from "@/src/lib/routes";
import { SPECIALISTS } from "@/src/lib/panel/specialists";

export const panelRoute = (slug: string, specialist?: string) => `${companyRoute(slug)}/panel${specialist ? `/${specialist}` : ""}`;

export function PanelNav({ slug, active }: { slug: string; active?: string }) {
  const pill = (on: boolean) => `inline-block rounded-full border px-3 py-1.5 ${on ? "border-accent bg-accent-soft text-accent" : "border-border bg-surface text-muted hover:text-accent"}`;
  return (
    <nav aria-label="Investment Panel" className="mt-4">
      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Investment Panel</p>
      <ul className="mt-2 flex flex-wrap gap-2 text-[0.82rem]">
        <li><Link href={panelRoute(slug)} aria-current={!active ? "page" : undefined} className={pill(!active)}>Overview</Link></li>
        {SPECIALISTS.map((s) => (
          <li key={s.id}><Link href={panelRoute(slug, s.id)} aria-current={active === s.id ? "page" : undefined} className={pill(active === s.id)}>{s.name.split(" ").slice(-1)[0]}</Link></li>
        ))}
      </ul>
    </nav>
  );
}
