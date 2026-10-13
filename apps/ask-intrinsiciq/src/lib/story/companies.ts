// Company configuration (data, not logic). To add a company: add a line here (`key` is its folder under companies/).
// Everything else — Story, Connections, Discoveries, question pages — is built from that company's own stored records.
// `withholdCommitmentRegister`: the lifecycle commitment register has not been reconciled with the annual-report evidence
// behind the company's approved commitment answers, so register-based statuses are not shown beside them.
export type CompanyConfig = { key: string; name: string; withholdCommitmentRegister?: boolean };
export const COMPANIES: Record<string, CompanyConfig> = {
  "sun-pharma": { key: "sun_pharma", name: "Sun Pharma", withholdCommitmentRegister: true },
  tanla: { key: "tanla", name: "Tanla Platforms" },
  ujjivan: { key: "ujjivan", name: "Ujjivan Small Finance Bank" },
  datapatterns: { key: "datapatterns", name: "Data Patterns (India)" },
};
