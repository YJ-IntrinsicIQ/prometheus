import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  notFound: () => { throw new Error("NOT_FOUND"); },
  redirect: (to: string) => { throw new Error(`REDIRECT:${to}`); },
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

import HomePage from "@/app/page";
import CompanyPage from "@/app/company/[companySlug]/page";
import QuestionPage from "@/app/company/[companySlug]/question/[questionId]/page";
import PanelPage from "@/app/company/[companySlug]/panel/page";
import SpecialistRoute from "@/app/company/[companySlug]/panel/[specialist]/page";
import { COMPANIES } from "@/src/lib/story/companies";
import { QUESTIONS } from "@/src/lib/story/question-view";
import { QuestionPending } from "./question-experience";
import QuestionsPage from "@/app/company/[companySlug]/questions/page";

const params = (p: object) => ({ params: Promise.resolve(p) as never });
// M59.4: availability is exactly the approval registry (91 pairs); the counts below are read from it, never assumed
const REGISTRY = Object.keys(JSON.parse(readFileSync(path.join(process.cwd(), "../../governance/approval_registry.json"), "utf8")).approvals);
const approvedFor = (slug: string) => REGISTRY.filter((k) => k.startsWith(`${COMPANIES[slug].key}:`)).length;

describe("the Cockpit is the application", () => {
  it("the landing page offers exactly the four supported companies", async () => {
    render(await HomePage());
    const options = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(options).toHaveLength(4);
    for (const c of Object.values(COMPANIES)) expect(options.some((o) => o.startsWith(c.name))).toBe(true);
    expect(screen.getByRole("link", { name: /explore|continue|open/i })).toHaveAttribute("href", expect.stringMatching(/^\/company\/[a-z-]+$/));
  });
  it.each(Object.keys(COMPANIES))("%s: the company page is the Story with Connections/Discoveries, the five questions and one banner", async (slug) => {
    render(await CompanyPage(params({ companySlug: slug })));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`${COMPANIES[slug].name}: The Story`);
    expect(screen.getByText("Investor view · approved intelligence only")).toBeInTheDocument();
    expect(screen.queryByText(/development preview|development flag|released feature|canary/i)).toBeNull();
    const nav = screen.getByRole("navigation", { name: "Investor questions" });
    for (const q of QUESTIONS) expect(nav.querySelector(`a[href="/company/${slug}/question/${q.id}"]`), q.id).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Companies" }).querySelectorAll("a")).toHaveLength(4);
  });
  it.each(QUESTIONS.map((q) => q.id))("Sun Pharma / %s renders the approved answer with evidence sections", async (questionId) => {
    render(await QuestionPage(params({ companySlug: "sun-pharma", questionId })));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(QUESTIONS.find((q) => q.id === questionId)!.title);
    expect(screen.getByText("Approved answer")).toBeInTheDocument();
    expect(screen.getByText("Source references")).toBeInTheDocument();
    for (const h of ["The answer", "Supporting evidence", "What remains unknown", "What to investigate next"]) expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();   // the five-part reading flow
    expect(screen.getByRole("navigation", { name: "You are here" })).toBeInTheDocument();
  });
  it("a catalog question without an approved answer says so, shows nothing in its place, and links only to certified answers", async () => {
    render(await QuestionPage(params({ companySlug: "tanla", questionId: "what-evidence-would-change-the-view" })));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("What evidence would change the view?");
    expect(screen.getByRole("heading", { name: "Answer not yet available" })).toBeInTheDocument();
    expect(screen.queryByText("Approved answer")).toBeNull();
    expect(screen.getByText(/awaiting evidence validation and certification/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /All Tanla Platforms questions/ })).toHaveAttribute("href", "/company/tanla/questions");
  });
  it("the pending page itself renders for a bare entry", () => {
    render(<QuestionPending slug="tanla" company="Tanla Platforms" available={[]} docs={[]} question={{ id: "x", title: "X?" }} familyTitle="Family" entry={null} related={[]} />);
    expect(screen.getByRole("heading", { name: "Answer not yet available" })).toBeInTheDocument();
  });
  it("unknown companies and unknown questions are 404; catalog ids served by a certified question redirect to it", async () => {
    await expect(CompanyPage(params({ companySlug: "acme" }))).rejects.toThrow("NOT_FOUND");
    await expect(QuestionPage(params({ companySlug: "acme", questionId: QUESTIONS[0].id }))).rejects.toThrow("NOT_FOUND");
    await expect(QuestionPage(params({ companySlug: "tanla", questionId: "not-a-question" }))).rejects.toThrow("NOT_FOUND");
    await expect(QuestionsPage(params({ companySlug: "acme" }))).rejects.toThrow("NOT_FOUND");
    await expect(QuestionPage(params({ companySlug: "tanla", questionId: "what-can-break-the-thesis" }))).rejects.toThrow("REDIRECT:/company/tanla/question/what-could-go-wrong");
    // a different-period question is NOT served by the whole-record delivery answer: it is served only by its own approved answer (M59.4)
    render(await QuestionPage(params({ companySlug: "tanla", questionId: "what-was-delivered-last-3-years" })));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("What was delivered in the last 3 years?");
    expect(screen.getByText("Approved answer")).toBeInTheDocument();
  });
  it.each(Object.keys(COMPANIES))("%s: the explorer lists all 38 questions in 6 families with the registry's approved answers", async (slug) => {
    render(await QuestionsPage(params({ companySlug: slug })));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`${COMPANIES[slug].name}: All questions`);
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(6);
    const n = approvedFor(slug);
    expect(screen.getAllByText("Certified answer")).toHaveLength(n);
    expect(screen.getAllByText("Answer pending")).toHaveLength(38 - n);
    expect(screen.getByText(new RegExp(`${n} of 38`))).toBeInTheDocument();
  });
  it("the explorer filters by search and by availability, on a phone-sized list as on a desktop one", async () => {
    render(await QuestionsPage(params({ companySlug: "sun-pharma" })));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "cash" } });
    expect(screen.getAllByRole("listitem").some((li) => /cash/i.test(li.textContent ?? ""))).toBe(true);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });
    const n = approvedFor("sun-pharma");
    fireEvent.click(screen.getByRole("button", { name: new RegExp(`Certified answer \\(${n}\\)`) }));
    expect(screen.getAllByText("Certified answer")).toHaveLength(n);
    expect(screen.queryByText("Answer pending")).toBeNull();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zzzz-nothing" } });
    expect(screen.getByText(/No question matches/)).toBeInTheDocument();
  });
});

describe("the Investment Panel is part of the Cockpit", () => {
  it.each(Object.keys(COMPANIES))("%s: overview shows five specialist cards and keeps the five management questions", async (slug) => {
    render(await PanelPage(params({ companySlug: slug })));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`${COMPANIES[slug].name}: Investment Panel`);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Benjamin Graham", "Philip Fisher", "Warren Buffett", "Charlie Munger", "Peter Lynch"]);
    expect(screen.getByRole("navigation", { name: "Investor questions" })).toBeInTheDocument();
    expect(screen.getAllByText("Open question")).toHaveLength(5);
    expect(screen.queryByText(/undervalued|overvalued|price target/i)).toBeNull();
  });
  it.each(["graham", "fisher", "buffett", "munger", "lynch"])("Sun Pharma / %s renders the five sections", async (specialist) => {
    render(await SpecialistRoute(params({ companySlug: "sun-pharma", specialist })));
    for (const h of ["What the evidence indicates", "Questions to investigate", "What remains uncertain", "Investor takeaway"]) expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/\?$/);
  });
  it("unknown specialists and companies are not found", async () => {
    await expect(SpecialistRoute(params({ companySlug: "sun-pharma", specialist: "soros" }))).rejects.toThrow("NOT_FOUND");
    await expect(PanelPage(params({ companySlug: "acme" }))).rejects.toThrow("NOT_FOUND");
  });
});
