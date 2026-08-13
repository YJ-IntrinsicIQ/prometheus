import { render, screen } from "@testing-library/react";
import { within } from "@testing-library/react";
import HomePage from "@/app/page";
import CompanyPage from "@/app/company/[companySlug]/page";
import QuestionPage from "@/app/company/[companySlug]/question/[questionId]/page";

describe("app routes", () => {
  it("shows the demo company selection on the landing page", async () => {
    const page = await HomePage();

    render(page);

    expect(screen.getByLabelText(/select a company/i)).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /datapatterns/i }),
    ).toBeInTheDocument();
  });

  it("shows the company header and first required question link", async () => {
    const page = await CompanyPage({
      params: Promise.resolve({ companySlug: "datapatterns" }),
    });

    render(page);

    expect(screen.getByText(/datapatterns/i)).toBeInTheDocument();
    expect(screen.getByText(/how the business is changing/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /what does the company do\?/i }),
    ).toHaveAttribute("href", "/company/datapatterns/question/what-does-company-do");
  });

  it("shows clearer back navigation on the answer page with evidence collapsed by default", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "did-past-claims-come-true",
      }),
    });

    render(page);

    expect(
      screen.getByRole("link", { name: /back to questions/i }),
    ).toHaveAttribute("href", "/company/datapatterns");
    expect(screen.getByText(/bottom line/i)).toBeInTheDocument();
    expect(screen.queryByText(/^progression$/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^confidence$/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /view supporting evidence/i }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it("renders a graceful non-crashing answer state for a partially sourced question", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "who-are-the-customers",
      }),
    });

    render(page);

    expect(screen.getAllByText(/defence integrator/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/^partially supported$/i)).toBeInTheDocument();
    expect(screen.queryByText(/business journey/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^customer roles$/i)).toBeInTheDocument();
  });

  it("renders the full business context on the main business-summary answer", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "what-does-company-do",
      }),
    });

    render(page);

    expect(screen.getByText(/business journey/i)).toBeInTheDocument();
    expect(screen.getByText(/products and services/i)).toBeInTheDocument();
    expect(screen.getByText(/detailed explanation/i)).toBeInTheDocument();
    expect(screen.getByTestId("reading-column")).toBeInTheDocument();
    expect(screen.getByTestId("wide-content-column")).toBeInTheDocument();
  });

  it("keeps the rendered answer-section order aligned with the intended reading flow", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "what-does-company-do",
      }),
    });

    const { container } = render(page);
    const readingColumn = screen.getByTestId("reading-column");
    const wideColumn = screen.getByTestId("wide-content-column");
    const pageText = container.textContent ?? "";
    const articleText = readingColumn.textContent ?? "";
    const detailedIndex = articleText.indexOf("Read detailed explanation");
    const journeyIndex = pageText.indexOf("Business journey");
    const productsIndex = pageText.indexOf("Products and services");

    expect(detailedIndex).toBeGreaterThan(-1);
    expect(journeyIndex).toBeGreaterThan(detailedIndex);
    expect(productsIndex).toBeGreaterThan(journeyIndex);
    expect(readingColumn.textContent).not.toContain("Business journey");
    expect(wideColumn.textContent).toContain("Business journey");
  });

  it("keeps factual business answers in the direct-answer layout", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "what-does-company-do",
      }),
    });

    render(page);

    expect(screen.queryByText(/bottom line/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^progression$/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/specialised defence and aerospace electronics maker/i),
    ).toBeInTheDocument();
  });

  it("renders a dedicated revenue flow and hides the full product catalogue on the revenue answer", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "how-does-it-make-money",
      }),
    });

    render(page);

    expect(screen.getByText(/revenue flow/i)).toBeInTheDocument();
    expect(screen.queryByText(/products and services/i)).not.toBeInTheDocument();
  });

  it("renders structured Buffett sections on the Buffett answer page", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "what-would-buffett-focus-on",
      }),
    });

    render(page);

    expect(screen.getByText(/what he may like/i)).toBeInTheDocument();
    expect(screen.getByText(/what he would question/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^what remains unproven$/i).length).toBeGreaterThan(0);
    expect(screen.getByTestId("wide-section-investor-lens")).toBeInTheDocument();
    expect(screen.queryByText(/^progression$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/earlier promise/i)).not.toBeInTheDocument();
  });

  it("renders exactly three next-question links without broken arrow-only text nodes", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "how-does-it-make-money",
      }),
    });

    render(page);

    const nextQuestions = screen.getByTestId("next-questions-section");

    const links = within(nextQuestions).getAllByTestId("next-question-card");
    expect(links).toHaveLength(3);
    links.forEach((link) => {
      expect(within(link).getByTestId("next-question-arrow")).toBeInTheDocument();
      expect(link.textContent?.trim()).not.toBe("→");
    });
    expect(within(nextQuestions).getByRole("link", { name: /explore another category/i })).toBeInTheDocument();
    expect(within(nextQuestions).getByText(/what to explore next/i)).toBeInTheDocument();
  });

  it("keeps the explore-another-category link outside the next-question card grid", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "what-does-company-do",
      }),
    });

    render(page);

    const nextQuestions = screen.getByTestId("next-questions-section");
    const grid = within(nextQuestions).getByTestId("next-question-grid");
    const exploreLink = within(nextQuestions).getByRole("link", {
      name: /explore another category/i,
    });

    expect(grid).not.toContainElement(exploreLink);
  });

  it("marks wide-layout sections separately from the reading column", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "what-does-company-do",
      }),
    });

    render(page);

    expect(screen.getByTestId("wide-section-products-services")).toBeInTheDocument();
    expect(screen.queryByTestId("wide-section-customer-roles")).not.toBeInTheDocument();
    expect(screen.getByTestId("business-journey-grid")).toBeInTheDocument();
  });

  it("renders the business journey with a desktop three-column-capable grid and direction below the stages", async () => {
    const page = await QuestionPage({
      params: Promise.resolve({
        companySlug: "datapatterns",
        questionId: "what-does-company-do",
      }),
    });

    const { container } = render(page);
    const grid = screen.getByTestId("business-journey-grid");
    const direction = screen.getByTestId("business-journey-direction");

    expect(grid.className).toContain("xl:grid-cols-3");

    const pageText = container.textContent ?? "";
    expect(pageText.indexOf("Capacity expansion phase")).toBeLessThan(
      pageText.indexOf("Stated direction"),
    );
    expect(direction.textContent).toContain("Stated direction");
  });
});
