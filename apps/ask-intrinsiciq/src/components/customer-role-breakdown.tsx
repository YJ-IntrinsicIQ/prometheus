import type { ResearchAnswerCard } from "@/src/types";

type CustomerRoleBreakdownProps = {
  customerRoles: NonNullable<ResearchAnswerCard["customerRoles"]>;
};

export function CustomerRoleBreakdown({
  customerRoles,
}: CustomerRoleBreakdownProps) {
  return (
    <section className="rounded-[24px] border border-border bg-[rgba(255,255,255,0.42)] p-5">
      <div data-testid="wide-section-customer-roles" />
      <p className="text-xs uppercase tracking-[0.24em] text-muted">
        Customer roles
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <RoleCard title="Who pays" items={customerRoles.payers} />
        <RoleCard
          title="Who integrates or partners"
          items={customerRoles.integratorsOrPartners}
        />
        <RoleCard title="Who uses" items={customerRoles.endUsers} />
        <RoleCard
          title="International customers"
          items={
            customerRoles.internationalCustomers.length > 0
              ? customerRoles.internationalCustomers
              : ["No distinct international-customer role is clearly separated."]
          }
        />
      </div>
      <p className="mt-4 text-sm leading-6 text-muted">
        {customerRoles.concentrationNote}
      </p>
    </section>
  );
}

function RoleCard({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-[18px] border border-border bg-surface px-4 py-4">
      <p className="text-[0.72rem] uppercase tracking-[0.16em] text-muted">
        {title}
      </p>
      <ul className="mt-3 space-y-2 text-sm leading-6 text-muted">
        {items.map((item) => (
          <li key={`${title}-${item}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
