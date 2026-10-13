// The five specialist frameworks: static definitions only. Each one is a perspective on the SAME evidence base, not a
// separate source of facts. `questions` maps EXISTING question ids (catalog or approved) to the specialist; a question may
// serve several specialists. `proposed` lists high-value questions the catalog does not yet contain (definitions only; no
// answers exist, and none are added to the catalog here).
export type SpecialistId = "graham" | "fisher" | "buffett" | "munger" | "lynch";

export type QuestionRef = { id: string; why: string };
export type ProposedQuestion = { id: string; title: string; why: string; needs: string };
export type Specialist = {
  id: SpecialistId;
  name: string;
  framework: string;
  coreQuestion: string;
  investorQuestion: string; // the one-line version shown on cards
  evaluates: string[];
  questions: QuestionRef[];
  proposed: ProposedQuestion[];
};

export const SPECIALISTS: Specialist[] = [
  {
    id: "graham", name: "Benjamin Graham", framework: "Valuation & margin of safety",
    coreQuestion: "Am I paying substantially less than the business is conservatively worth?",
    investorQuestion: "Is it conservatively valued?",
    evaluates: ["Financial strength and balance-sheet resilience", "Earnings history and stability", "Cash behind the earnings", "Conservative valuation and margin of safety"],
    questions: [
      { id: "are-profits-converting-into-cash", why: "Whether reported earnings are backed by cash." },
      { id: "is-working-capital-a-concern", why: "Whether growth is tying up cash that a downturn could trap." },
      { id: "are-per-share-economics-improving", why: "The per-share inputs any valuation would need." },
      { id: "what-would-graham-worry-about", why: "The catalog's own Graham question." },
      { id: "how-is-capital-allocated", why: "Dividends, debt repayment and what capital leaves the business." },
      { id: "what-can-break-the-thesis", why: "Downside scenarios the margin of safety must cover." },
    ],
    proposed: [
      { id: "how-stable-are-earnings-across-years", title: "How stable are earnings across years?", why: "Earnings history is the base of any conservative valuation.", needs: "Deterministic from financial trends; same-basis years only." },
      { id: "is-the-balance-sheet-resilient-in-a-downturn", title: "Is the balance sheet resilient in a downturn?", why: "Downside protection depends on debt, liquidity and cash needs together.", needs: "Debt, liquidity and maturity data, including interest coverage." },
      { id: "what-is-a-conservative-estimate-of-intrinsic-value", title: "What is a conservative estimate of intrinsic value?", why: "The question Graham's test turns on.", needs: "A market price and a sourced valuation method; Prometheus holds no market data." },
    ],
  },
  {
    id: "fisher", name: "Philip Fisher", framework: "Business quality & growth",
    coreQuestion: "Does this business possess the qualities required for durable long-term growth?",
    investorQuestion: "Is it a high-quality growth business?",
    evaluates: ["Growth opportunities and their drivers", "Product development, innovation and R&D", "Execution against stated plans", "Management quality and candour", "Long-term reinvestment"],
    questions: [
      { id: "what-is-management-commentary-saying", why: "What management says about growth and priorities." },
      { id: "what-projects-are-underway", why: "Reinvestment in new capacity and products." },
      { id: "how-is-capacity-changing", why: "Whether the capacity to grow is being built." },
      { id: "where-would-fisher-be-curious", why: "The catalog's own Fisher question." },
      { id: "what-has-management-promised", why: "What management committed to, as a test of its plans." },
      { id: "what-did-management-actually-deliver", why: "Execution against those commitments, over the whole record." },
      { id: "what-was-delivered-last-3-years", why: "What was delivered most recently." },
      { id: "how-good-is-management", why: "Management consistency and candour." },
    ],
    proposed: [
      { id: "how-productive-is-rd-spending", title: "How productive is R&D spending?", why: "Fisher's central test of growth quality.", needs: "R&D expense series and pipeline outcomes; neither is in the records." },
      { id: "what-is-the-growth-runway", title: "What is the growth runway?", why: "Whether the market and products allow years of growth.", needs: "Market-size and product-pipeline evidence." },
      { id: "how-strong-is-the-competitive-position", title: "How strong is the competitive position?", why: "Growth that competitors can erode is not durable.", needs: "Market-share and peer evidence." },
    ],
  },
  {
    id: "buffett", name: "Warren Buffett", framework: "Business economics & capital allocation",
    coreQuestion: "Would I want to own this business for the next ten years?",
    investorQuestion: "Are its economics and capital allocation attractive?",
    evaluates: ["Return on capital and margins", "Reported earnings versus owner earnings versus cash", "Capital allocation", "Management trustworthiness", "Durability of cash generation"],
    questions: [
      { id: "what-is-owner-earnings", why: "The estimate of cash an owner could take out." },
      { id: "are-profits-converting-into-cash", why: "Whether profit turns into cash." },
      { id: "how-is-capital-allocated", why: "Where retained cash went." },
      { id: "which-investments-created-value", why: "Whether past investments earned their keep." },
      { id: "what-is-the-return-on-capex", why: "The return on capital reinvested." },
      { id: "what-incentives-matter", why: "Whether management's incentives match owners'." },
      { id: "how-good-is-management", why: "Management consistency." },
      { id: "what-would-buffett-focus-on", why: "The catalog's own Buffett question." },
    ],
    proposed: [
      { id: "does-the-business-have-a-durable-moat", title: "Does the business have a durable moat?", why: "Durable returns need a defence against competition.", needs: "Pricing power, share and margin-persistence evidence against peers." },
      { id: "what-return-does-incremental-capital-earn", title: "What return does incremental capital earn?", why: "Compounding depends on reinvestment returns.", needs: "Return on capital employed and segment-level returns." },
      { id: "how-much-of-earnings-can-owners-take-out", title: "How much of earnings can owners take out?", why: "The gap between reported profit and distributable cash.", needs: "The maintenance versus growth capex split, which no company here discloses." },
    ],
  },
  {
    id: "munger", name: "Charlie Munger", framework: "Risks & inversion",
    coreQuestion: "What could cause this investment thesis to be wrong?",
    investorQuestion: "What could go wrong with the thesis?",
    evaluates: ["Inversion: ways to fail", "Incentives", "Accounting and financial warning signs", "Competitive threats", "Management contradictions and hidden assumptions"],
    questions: [
      { id: "what-can-break-the-thesis", why: "The risk record, year by year, and what could break the thesis." },
      { id: "what-evidence-would-change-the-view", why: "What would falsify the thesis." },
      { id: "which-disclosure-is-missing", why: "Where silence deserves a question." },
      { id: "what-needs-management-clarification", why: "Open items for management." },
      { id: "what-did-management-actually-deliver", why: "Promises against actions, over the whole record." },
      { id: "what-has-management-promised", why: "The promises to test." },
      { id: "what-incentives-matter", why: "Incentives that could distort decisions." },
      { id: "what-would-munger-avoid", why: "The catalog's own Munger question." },
    ],
    proposed: [
      { id: "what-accounting-warning-signs-exist", title: "What accounting warning signs exist?", why: "Cash conversion, receivables and basis changes are checkable.", needs: "Deterministic from financial trends and working-capital records." },
      { id: "which-assumptions-is-the-thesis-resting-on", title: "Which assumptions is the thesis resting on?", why: "Hidden assumptions are the usual source of avoidable mistakes.", needs: "A defined thesis to test; derived from the other specialists' open questions." },
      { id: "what-do-management-incentives-reward", title: "What do management incentives reward?", why: "People do what they are paid to do.", needs: "Remuneration and ESOP terms, which are not in the structured records." },
    ],
  },
  {
    id: "lynch", name: "Peter Lynch", framework: "Business simplicity & growth opportunities",
    coreQuestion: "Can I understand how this company makes money and where future growth could come from?",
    investorQuestion: "Is it understandable, and where could growth come from?",
    evaluates: ["A simple explanation of the business", "Revenue drivers", "Customers and industry", "Growth profile and runway", "Valuation relative to growth"],
    questions: [
      { id: "what-does-company-do", why: "The one-paragraph business explanation." },
      { id: "who-are-the-customers", why: "Who pays, and how concentrated that is." },
      { id: "how-does-it-make-money", why: "The revenue model." },
      { id: "did-execution-lead-to-outcomes", why: "Whether activity turned into results." },
      { id: "how-is-capacity-changing", why: "Capacity for future growth." },
      { id: "how-is-capital-allocated", why: "Where growth is being funded." },
      { id: "are-per-share-economics-improving", why: "Growth in the numbers a shareholder owns." },
      { id: "how-would-lynch-explain-it", why: "The catalog's own Lynch question." },
    ],
    proposed: [
      { id: "what-drives-revenue-growth", title: "What drives revenue growth?", why: "Growth that cannot be explained cannot be relied on.", needs: "Segment or geography revenue history; only one company here has it." },
      { id: "where-could-the-next-leg-of-growth-come-from", title: "Where could the next leg of growth come from?", why: "The runway question.", needs: "Pipeline, market-size and capacity evidence." },
      { id: "how-does-valuation-compare-with-growth", title: "How does valuation compare with growth?", why: "Lynch's price-versus-growth test.", needs: "A market price; Prometheus holds no market data." },
    ],
  },
];

export const specialistById = (id: string) => SPECIALISTS.find((s) => s.id === id);
