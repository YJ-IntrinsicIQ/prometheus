import { fireEvent, render, screen } from "@testing-library/react";
import { QuestionNavigator } from "@/src/components/question-navigator";
import { getCompanyResearchView } from "@/src/lib/ask-intrinsiciq";

describe("QuestionNavigator", () => {
  it("keeps only one category expanded at a time", async () => {
    const company = await getCompanyResearchView("datapatterns");

    if (!company) {
      throw new Error("Expected company research view to exist");
    }

    render(<QuestionNavigator company={company} />);

    expect(
      screen.getByRole("button", { name: /understand the business/i }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/what does it do/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /financials/i }));

    expect(
      screen.getByRole("button", { name: /understand the business/i }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getByRole("button", { name: /financials/i }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.queryByText(/get the business model and positioning in one clean first read\./i),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/profit to cash/i)).toBeInTheDocument();
  });

  it("shows five business questions and a subtle progress cue in the active category", async () => {
    const company = await getCompanyResearchView("datapatterns");

    if (!company) {
      throw new Error("Expected company research view to exist");
    }

    render(<QuestionNavigator company={company} />);

    expect(screen.getByText(/understand 1\/5 explored/i)).toBeInTheDocument();
    expect(screen.getByText(/what does the company do\?/i)).toBeInTheDocument();
    expect(screen.getByText(/who are the customers\?/i)).toBeInTheDocument();
    expect(screen.getByText(/how does it make money\?/i)).toBeInTheDocument();
    expect(
      screen.getByText(/what makes the offering important\?/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/where is evidence thin\?/i)).toBeInTheDocument();
  });

  it("renders all five categories with four to five questions each", async () => {
    const company = await getCompanyResearchView("datapatterns");

    if (!company) {
      throw new Error("Expected company research view to exist");
    }

    render(<QuestionNavigator company={company} />);

    expect(company.categories).toHaveLength(5);
    expect(company.categories.every((category) => category.questions.length >= 4)).toBe(
      true,
    );
    expect(company.categories.every((category) => category.questions.length <= 5)).toBe(
      true,
    );
  });
});
