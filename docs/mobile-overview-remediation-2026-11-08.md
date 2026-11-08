# Mobile Overview remediation — user-reported 390px defects

Evidence: live Android Chrome screenshot supplied 8 November 2026. This change targets the observed Overview layout, not a complete reference-fidelity signoff.

| ID | Severity | Observed issue | Implementation |
|---|---|---|---|
| MOB-01 | High | Breadcrumb and page heading both say Overview | Mobile context bar hidden when no workflow steps are present; progress context remains visible in migration workflow |
| MOB-02 | High | Three independent tall KPI cards squeeze labels at 390px | Single grouped summary strip; value-first typographic hierarchy and minimal internal borders |
| MOB-03 | Medium | "Recorded example" repeats beneath every KPI | Redundant text removed; public sample identified once in the migration record |
| MOB-04 | High | Promotional-card layout consumes the first viewport | Semantic record with compact header, model facts and clearly placed inspection action |
| MOB-05 | Medium | Original model identifier breaks into disjoint fragments | Full-width label/value rows on mobile; monospace text has intrinsic min-width safeguards |
| MOB-06 | Medium | Result status detached below unrelated details | Result kept inside the same dense facts list; semantic status colors retained |
| MOB-07 | Medium | Five tight top-level navigation destinations with tiny targets | Mobile primary navigation has four items; Settings remains available from workspace preferences |
| MOB-08 | Medium | Header controls have undersized mobile hit regions | Enlarged search, sign-in and preference controls |
| MOB-09 | High | Existing browser acceptance never checks these compositional failures | 320/360/390 mobile assertions for duplicate context, KPI density and activity position |
| MOB-10 | Medium | Dead promotional-card styles increase cascade ambiguity | Removed obsolete per-card selectors from UI and workbench CSS |

Acceptance scope: Firefox rendered at 320–1440px using the actual application and recorded guest API. No paid inference. Layout, interaction, and page-level overflow checks are distinct from full accessibility and visual-reference acceptance. Chromium/WebKit and manual screen reader review remain necessary.
