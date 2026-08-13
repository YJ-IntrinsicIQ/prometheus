"use client";

import { useState } from "react";
import { QuestionCategory } from "@/src/components/question-category";
import type { CompanyResearchView } from "@/src/types";

type QuestionNavigatorProps = {
  company: CompanyResearchView;
};

export function QuestionNavigator({ company }: QuestionNavigatorProps) {
  const [openCategoryId, setOpenCategoryId] = useState(
    company.categories[0]?.id ?? "understand-the-business",
  );

  return (
    <div className="space-y-4">
      {company.categories.map((category) => (
        <QuestionCategory
          key={category.id}
          companySlug={company.company.companySlug}
          category={category}
          isOpen={category.id === openCategoryId}
          onOpen={() => setOpenCategoryId(category.id)}
          progressText={
            category.id === openCategoryId
              ? `${category.title.split(" ")[0]} ${category.displayOrder}/${company.categories.length} explored`
              : null
          }
        />
      ))}
    </div>
  );
}
