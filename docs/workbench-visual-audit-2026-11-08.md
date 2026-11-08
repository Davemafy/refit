# Refit — frontend visual system audit (8 November 2026)

## Scope and evidence integrity

This pass modifies the existing vanilla JavaScript workspace rather than replacing the application architecture. It was exercised against the public read-only application at `https://80.240.30.92/app`, with development CSS/JS substituted at the network asset layer. Actual live models and paid inference were **not** invoked during these tests. The uploaded strict visual reference archive was registered but its raw bytes were not accessible in the execution filesystem; a literal pixel comparison against each Inngest/Braintrust frame is therefore **not verified**. The reference-level map below is a functional mapping, not an assertion of measured pixel identity.

Baseline: 1440×900 screenshot and 390×844 screenshot of public Overview, plus 1440×900 captures of Agents, Import, Runs, Evidence and Migration Review. Candidate: desktop and mobile Overview/Import/Review, component fixture in light/dark, 5-width Firefox functional tests. Screenshot artifacts are local browser-test output, not an external image-generation mockup.

## Design rationale and implementation map

| Refit surface | Primary reference class | Implementation contract |
| --- | --- | --- |
| Shell + Overview | Inngest operational workspace | 48px top context, 220px desktop nav, 48px local context bar; compact activity list, restrained borders, no marketing treatment |
| Agents | Inngest listing and selection | Source link and explicit inspect action; runtime/provider visibility; removal is separate from source adjustments |
| Import: source | Inngest guided operational setup | Single source-selection panel, GitHub/ZIP switch, advanced fields disclosed only on request; no redundant decorative step tiles |
| Import: inspect/configure | Developer integration workbench | Detected execution boundary, explicit independent checks and bounded authorization; unsupported source presents recovery, not destructive reset |
| Runs | Inngest tabular operations | Tight row rhythm, numeric alignment, status grammar, local search/filtering, contextual navigation |
| Run Trace | Inngest nested trace | Collapsible phase/case groups, event timestamps, selection controls, separate event/inspector scroll |
| Evidence | Braintrust investigation workspace | Connected evidence index + inspection panel, URL state and stable selected observation |
| Comparison | Refit-specific | Immediate run verdict plus paired source/replacement checks, drill-down to recorded evidence, narrow-screen vertical comparisons |
| Component bench | Existing frontend primitives | Explicit light/dark states, long identifiers, empty/error/disabled/loading fixtures, table and trace checks |

## Visual foundation

Workspace semantic tokens: `--bg`, `--panel`, `--raised`, `--field`, `--line`, `--line2`, `--ink`, `--sub`, `--muted`, `--work-accent`, `--work-action`, `--work-positive`, `--work-negative`, `--work-warning`, their semantic backgrounds, plus `--work-focus`, `--work-radius`, `--work-control-height`, `--work-ease` and `--work-shadow`. Dark/light derive from separate palette declarations. Technical content uses Geist Mono and tabular figures. Controls have workspace-owned minimum sizes, consistent feedback and `:focus-visible` affordances. Reduced-motion preference disables motion across the workspace.

Component contracts: action buttons support primary/secondary/danger/disabled/busy, use fixed density and focus outlines; chips distinguish verified, failed, pending, neutral; fields carry helper/error text with native labels; tables use scoped column headings and tabular metrics; navigational selection is reflected through `aria-current` or `aria-pressed`; trace selection updates inspector from keyboard as well as pointer; source import switches both required fields and its form mode; no backend data is synthesized by UI.

Desktop shell has one scrolling main region and an independently scrollable sidebar; mobile restores document scrolling. Nested evidence/trace panes retain their own scroll offsets on live refresh. Internal panels use intrinsic minimum widths to prevent page-level horizontal overflow.

## Defect register and disposition

| ID | Severity | Before | Treatment | Verification |
| --- | --- | --- | --- | --- |
| VIS-01 | High | Migration verdict had a darker, oversized banner visually disconnected from the rest of the light operational UI | Converted verdict to semantic surface tokens, compact type scale and restrained evidence summary | Candidate light desktop/mobile capture visually reviewed |
| VIS-02 | High | Desktop document and inspection regions shared poorly defined scroll ownership | Fixed shell grid height, main flex overflow, sidebar scroll and nested trace inspector | Firefox at 768–1440px: viewport document stays at 900px height; main scrolls |
| VIS-03 | Medium | Import included redundant three-card process explanation beneath actual progress indicator | Removed duplicate cards; maintained contextual source field and step indicator | Candidate guest import and button navigation |
| UX-04 | High | Unsupported source lacked a low-friction way to adjust and retry without deleting prior work | Source recovery section preserves imported snapshot and runs; handles GitHub and ZIP alternatives; clears stale `?project=` URL | Static component state, JS path review; full authenticated integration pending |
| A11Y-05 | Medium | Trace arrows moved focus but did not select corresponding evidence | Keyboard navigation now updates `aria-pressed`, URL and inspector | Firefox interaction test |
| VIS-06 | Medium | Inconsistent form/control/status padding, radius and focus styling | Normalized with workspace-owned tokens; removed two `!important` comparison padding rules | Light/dark component bench |
| VIS-07 | Medium | Long technical IDs and dense tables risk wrapping/overflow | Monospace numeric treatment, constrained trace layout, mobile vertical comparisons | 390/768/1024/1366/1440 browser checks, no document overflow |
| REF-08 | Blocker | Original-resolution reference ZIP and recordings cannot be read in execution runtime | **Unresolved**; do not claim exact reference fidelity until usable bytes are provided | File materialization returned a path, filesystem read did not find file |
| TEST-09 | Medium | Existing browser suite assumed old guest CTA text | Updated suite to assert “Inspect recorded run” | CI workflow required before full acceptance |

## Browser checks and limitations

Using Playwright Firefox against the live guest API with candidate asset interception: 390, 768, 1024, 1366, 1440px all rendered Overview, Import and Migration Review with **zero document-level horizontal overflow** and zero JavaScript page errors. Evidence and Trace tabs retained an inspected selection; 50 event entries appeared unfiltered, 14 in the model filter. The evidence inspector displayed details after selection. Component fixture passed viewport-fit checks at 390px, and light/dark captures were inspected. The test runner captures screen states from actual browser rendering.

Do **not** treat these as a completed WCAG 2.2 AA audit or final cross-browser acceptance: keyboard/focus/copy/contrast need repeated automated and manual checks, and Chromium/WebKit should execute in a CI runner with adequate memory. In the DevMCP E2B machine, Chromium crashed under limited memory; Firefox was the primary live browser. The production URL and exact deployed revision must be checked separately from local screenshots. These findings are scoped to the public sample and do not prove private import or real paid-run success.

## Production release requirements

1. Run fixture + app browser suites, including keyboard and theme checks, on the exact committed SHA.
2. Verify GitHub workflow status on the commit before invoking the pinned host deployment bridge.
3. Confirm `GET /api/application/release` matches the exact committed SHA, inspect live HTTPS screenshots and trace interaction on the deployed assets.
4. Record unresolved differences against the original reference contract once its images and recordings are accessible.
