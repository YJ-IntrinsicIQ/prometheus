// M63/G5: UI strings that describe a missing record must use an absence state (not extracted / not disclosed / not applicable), never assert silence or non-existence.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const files = ["src/lib/story/connections.ts", "src/lib/panel/build-panel.ts", "src/lib/story/story-events.ts", "src/lib/story/discoveries.ts"].map((f) => [f, readFileSync(path.join(process.cwd(), f), "utf8")] as const);

describe("G5 absence wording in the rendering code", () => {
  it.each(files)("%s asserts no silence or non-existence from a missing record", (_f, src) => {
    expect(src).not.toMatch(/records are silent/i);
    expect(src).not.toMatch(/"No evidence found"|"Not disclosed(?: in the records)?"/);
    expect(src).not.toMatch(/: not disclosed"|are not disclosed in the records|Not disclosed in the sources searched|is disclosed for these projects/i);
    expect(src).not.toMatch(/none has a recorded management response/i);
    expect(src).not.toMatch(/has a recorded management response/i);
    expect(src).not.toMatch(/reporting basis not stated(?! in)/i);
    expect(src).not.toMatch(/are not in the records, so the length/i);
    expect(src).not.toMatch(/Interest coverage is not reported in the records|Return on capital employed is not available|years of revenue is not stated|is not stated for \$\{unknown\}/i);
  });
  it("does not say customer concentration is unknown (the filings disclose it); it says it is not extracted into the records", () => {
    const panel = files.find(([f]) => f.endsWith("build-panel.ts"))![1];
    expect(panel).not.toMatch(/[Cc]ustomer concentration is not known/);
    expect(panel).toMatch(/[Cc]ustomer-concentration figures are not extracted into the records/);
  });
  it("the management-response line says the link, not the response, is what is missing", () => {
    const panel = files.find(([f]) => f.endsWith("build-panel.ts"))![1];
    expect(panel).toMatch(/not linked in the extracted records, which does not show that no response exists/);
  });
});
