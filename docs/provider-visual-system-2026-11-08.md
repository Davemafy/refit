# Refit · Provider visual identity and investigation layout

Implementation: standalone HTML/CSS/JS, no framework migration.

## Design changes

- Mobile navigation is disclosed from a native details menu. One visible page heading remains; workspace preferences are accessible through the avatar with no dangling chevron.
- Overview shows the actual original and replacement model identifiers using provider marks, a connective migration path and ticks derived from recorded `case_completed` event verdicts.
- Runs uses the same provider identities in operational tables and narrow-screen records, with a visible heading and usable local filters.
- Evidence uses a dedicated investigation list that opens the selected recorded evidence view, rather than reusing the Runs table.
- Comparison and trace headers reuse provider identities. The direct migration review no longer repeats the title in a redundant mobile progress bar.
- Import presents the read-only sample as a model-to-model comparison. Empty states have a simple, inline source → adaptation → evidence SVG, not stock artwork.

## Asset provenance and security

The eight provider symbols in `web/application/icons` were retrieved from `@lobehub/icons-static-svg@1.102.0` (LobeHub Icons, MIT); the license text is included alongside the SVGs. Recognition uses a fixed, explicit model-identifier mapping, and falls back to a generic glyph for unknown models. The app serves assets through an explicit server-side allowlist with a same-origin image CSP and no runtime third-party icon requests.

## Acceptance and caveats

Actual Firefox snapshots for the guest workspace at mobile 390×844 and desktop 1440×844 are stored in `docs/visual-evidence/provider-visual-*.jpg`. The first rendered review also checked 320px and 768px: no page-level horizontal overflow and no JavaScript page errors. The source-to-replacement and proof counts are produced only from recorded API data. These checks do not constitute a full WCAG 2.2 audit, authenticated import acceptance, WebKit verification, or pixel-level equivalence to the Inngest/Braintrust reference archive.
