import type { ReactNode } from "react";

type AnswerPageShellProps = {
  children: ReactNode;
};

type ReadingColumnProps = {
  children: ReactNode;
};

type WideContentColumnProps = {
  children: ReactNode;
};

export function AnswerPageShell({ children }: AnswerPageShellProps) {
  return (
    <div
      data-testid="answer-page-shell"
      className="min-w-0 w-full max-w-[1200px] px-4 md:px-6 lg:px-8"
    >
      {children}
    </div>
  );
}

export function ReadingColumn({ children }: ReadingColumnProps) {
  return (
    <div
      data-testid="reading-column"
      className="min-w-0 w-full max-w-[800px]"
    >
      {children}
    </div>
  );
}

export function WideContentColumn({ children }: WideContentColumnProps) {
  return (
    <div
      data-testid="wide-content-column"
      className="mt-12 min-w-0 w-full space-y-12 md:mt-14 md:space-y-14"
    >
      {children}
    </div>
  );
}
