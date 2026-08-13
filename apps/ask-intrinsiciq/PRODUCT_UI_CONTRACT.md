# Ask IntrinsicIQ v0

## Product principle

One screen. One thought. One next action.

## Routes

1. `/`
   Company search landing screen with Ask IntrinsicIQ branding, the tagline “Understand businesses through investor-grade questions.”, and a single company select flow driven by valid Ask IntrinsicIQ output directories.

2. `/company/datapatterns`
   Curated question navigator for the approved v0 company output.

3. `/company/datapatterns/question/what-does-company-do`
4. `/company/datapatterns/question/are-profits-converting-into-cash`
5. `/company/datapatterns/question/what-would-buffett-focus-on`
6. `/company/datapatterns/question/what-are-key-risks`

Focused answer routes are implemented through the shared dynamic route `/company/[companySlug]/question/[questionId]` and statically generated for the approved v0 question set above.

## Categories

- Understand the Business
- Financials
- Management
- Investor Panel
- Risks and Diligence

## Interaction rules

- Landing screen stays centered and calm.
- The landing screen should list only companies that have a valid canonical Ask IntrinsicIQ output directory in the local repository. A development fixture may appear only when canonical output is absent and must be visibly marked as development-only.
- Only one category is expanded at a time.
- Maximum five visible questions.
- The default open business category may show 4–5 questions in v0.
- A subtle category progress cue may appear for the active category (for example `Business 1/5 explored`).
- Use one subtle `Recommended next` indicator only.
- Clicking a question moves directly to its focused answer route.
- Questions must resolve through the canonical backend answer catalog. When an answer is unavailable in the current environment, the screen should render a calm unavailable state rather than a broken link.
- Focused answer pages must show:
  - one subtle answer-status pill using only customer-safe wording:
    - `Evidence supported`
    - `Partially supported`
    - `Not supported by available evidence`
    - `Unavailable in current release`
  - clear `← Back to questions` navigation
  - selected question as the main heading
  - direct answer first
  - short explanation
  - maximum four supporting points
  - one compact uncertainty note that does not dominate the answer
  - collapsed `View supporting evidence` by default
  - exactly three next suggested questions
  - quiet `Explore another category` action
  - placeholder copy when the answer has not yet been fully authored in the demo model
- No custom questions in v0.
- No Research Cockpit in v0.
- No cockpit link, no sidebar, and no chat transcript layout.
- No buy, sell or hold language.
- No valuation output.
- Evidence remains available through progressive disclosure.
- Missing information must remain visible.
- The interface must not expose raw JSON or internal Prometheus terminology.
- UI components must consume typed view-model data only. If real company-memory artifacts are read, that work must happen behind the canonical server-only loader boundary under `src/lib/ask-intrinsiciq/`, and it must sanitize internal filenames, artifact labels, diagnostics, and pipeline wording before anything reaches the UI.
- The typed answer model may distinguish `sourced`, `partially_sourced`, `not_supported`, and `placeholder`, but all four states must render through the same calm focused-answer layout without adding dashboards, warning consoles, or debug surfaces.
- The canonical Prometheus-to-frontend data shape is defined separately in `ASK_INTRINSICIQ_VIEW_MODEL_CONTRACT.md`. UI work may add renderer-facing compatibility types, but no backend-facing frontend contract is valid unless it is reflected there.

## Visual rules

Warm ivory background.
Deep navy typography.
Muted emerald for meaningful interaction.
Restrained gold for uncertainty or diligence.
Editorial serif for important conclusions.
Clean sans-serif for interface controls.
Generous whitespace.
Soft borders.
Minimal shadows.
Calm, premium, serious presentation.
No dashboard grids or decorative AI effects.
No trading terminal feel.
No red/green market noise.

## Deferred items

- Custom questions
- Research Cockpit
- Client-visible live backend/API integration
- Authentication
- Notes and pinning
- Historical comparison
