import type { ReactNode } from "react";

type AppFrameProps = {
  children: ReactNode;
};

export function AppFrame({ children }: AppFrameProps) {
  return (
    <div className="page-shell">
      <div className="content-frame">{children}</div>
    </div>
  );
}
