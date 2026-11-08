# Refit workspace reference and acceptance

The reference recording is 84.4 seconds at 1364 × 676. The supplied stills are 1366 × 768, apart from embedded browser chrome in the Apps capture. The recording was inspected across its full duration using a one-second contact sheet. Pixel measurements are approximate. The recording establishes visible states and transitions. It does not establish source CSS, exact animation curves, or keyboard behavior.

| Recording | Observed structure and behavior | Refit adaptation and data |
|---|---|---|
| 00:00–00:08 | Approximately 48px global strip above an inset frame and 220px rail. Workspace and environment at left. Overview uses a row of metrics, an operational flow and a lower table. Around 00:04 the palette appears over a dimmed shell with a search row and grouped actions. Dark changes to light around 00:07. | Same header and rail geometry. Real run activity and request capacity. Grouped navigation, actions, agents and runs in a modal search. Mobile replaces the rail with a short navigation row. |
| 00:08–00:20 | Light theme preserves composition and changes panel, text and border contrast. Apps shows a centered empty state around 00:12. A light palette is visible around 00:14. By 00:19 the listing is dark. | Shared workspace tokens. Appearance menu uses system, light or dark preferences and keeps the selected setting across navigation. Empty private workspaces point to source import. |
| 00:20–00:44 | The active sidebar row follows the listing. A shallow toolbar and column scaffold persist when rows are absent. Filters and refresh operate without replacing the shell. The video shows brief loading and confirmation states. | Runs use real status, model pair, start time and duration when recorded. Search and status filters retain the list. Agents use pinned revision, detected runtime and integration boundary. Mobile run rows stack. |
| 00:44–00:56 | Metrics appears around 00:46. The status graphic is framed separately from failures and volume. Filters sit above diagnostics. | Use real capacity and recorded counts. Do not project a distribution from absent run data. |
| 00:56–01:04 | Onboarding shows one step and a separate guide. A compact command surface and connection status are visible. | Public example gives immediate access to a recorded migration. Imported source progresses through inspection, configuration and authorized execution. Service boundaries use connector guidance. |
| 01:04–01:20 | Webhooks uses global navigation, a narrow resource pane and a main detail area. The navigation rail visibly collapses and expands around 01:09–01:11. | Trace and Evidence use an event index with a contextual inspector. Small screens stack the panes. Refit keeps a fixed desktop rail. |
| 01:20–01:24 | Account control is at the right edge of the global strip. The menu exposes theme controls and light briefly appears around 01:19–01:20. | Appearance and account settings sit in the same global position. The browser checks persisted theme, focus, reduced motion and keyboard access. |
| Execution-trace reference | Indented disclosures, selected rows, durations and a separate detail area make nested operations scannable. | Refit groups actual phases and sandbox case boundaries. It shows measured durations, event time, observed tool requests and verified checks with independent semantics. |

## Acceptance matrix

| Dimension | Browser acceptance and known limits |
|---|---|
| Shell proportions | Assert 48px header and 220px rail at 1366px. |
| Navigation | Overview, Agents, Runs, Evidence, Settings and Import are visited directly. |
| Typography | Geist body, monospace IDs, compact headings and numerical durations. Inspect the screen captures. |
| Theme | Both themes captured on workspace views. Preference survives full navigation and refresh. |
| Tables | Real owner-scoped fields and recorded sample. Duration falls back to an em dash when unavailable. |
| Filters | Existing Firefox suite checks run and trace filters. Agent search filters the current project list. |
| Dialogs | Native modal gives background inertness and Escape dismissal. |
| Command palette | Search highlight, no matches, arrow selection, Enter, Escape and focus restoration. |
| Empty states | Private workspace exposes import. The public workspace exposes recorded evidence. |
| Onboarding | Public sample opens without an account. Import still requires explicit evaluation checks and inference authorization. |
| Execution trees | Confirm nested disclosures and recorded event inspection. |
| Selection | Selected event survives refresh through the run URL. |
| Split pane | Trace and Evidence use an index and inspector. Mobile stacks the panes. |
| Motion | Reduced motion tested. No timings are inferred from the reference recording. |
| Keyboard | Palette shortcut and navigation, trace row navigation and Enter selection. |
| Responsive | Check full document width at 390, 768, 1024, 1366 and 1440px. |
| Real data | Public verification uses previously recorded production observations. |
| Performance | Trace rows capped to the latest 150 matching entries. No cross-device latency benchmark. |
| Accessibility | Focus, labeled controls, modal and overflow checks. A complete screen-reader or WCAG audit is separate. |
| Workflow simplicity | Public example requires no account or inference. A managed run still requires a supported boundary and independent checks. |

Run `node tests/browser_workbench.mjs` with Playwright Firefox installed for local HTTPS. Set `REFIT_WORKBENCH_URL` for production and `REFIT_WORKBENCH_OUTPUT` to collect captures. The suite makes no paid model requests.
