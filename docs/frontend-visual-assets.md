# Refit frontend visual assets

## Provenance and usage

Visual assets come from the **open-source Flowbite Illustrations** collection, designed by Berin Holy and Robert Tanislav, integrated by Zoltán Szőgyényi.

- Original library: https://github.com/themesberg/flowbite-illustrations
- Gallery: https://flowbite.com/illustrations/
- License: MIT. Full original notice preserved in \`web/application/illustrations/LICENSE-MIT.txt\`.
- Files copied from \`src/3d/{dark,light}/\`. Filenames are kept intact in our source tree, and the public HTTP allowlist exposes shorter stable URLs.

| Interface use | Original illustration |
| --- | --- |
| Product preview: isolated execution | \`woman-working-servers\` |
| Source import and empty agents | \`document-folders\` |
| First-time import / evaluation and empty runs | \`man-working-programs\` |
| Verification / empty evidence | \`password-lock-key\` |
| Load failure / recovery | \`laptop-server-error\` |

Both light and dark SVG variants are bundled. They are loaded from **same-origin static asset routes**, with no external asset CDN or third-party request, no remote model-generated content and no runtime image generation. The existing SVG provider marks continue to come from the licensed model-logo set already included in Refit.

## Data integrity

The marketing preview at \`/\` loads \`/api/application/demo\`, an allowlisted, sanitized historical execution. The UI derives model identifiers, pass/fail bars and worker cleanup counts from that response. If it is unavailable or has invalid provenance, no verified counts are shown.

**The preview is read-only**: it cannot submit a run or generate a diagnostic. The interactive application continues to rely on its authenticated, owner-scoped API. Illustrations are decorative, hidden from assistive technology, and are not substitutes for evaluation evidence.

## Guardrails

- A sourced illustration must reinforce an action or concept, not serve as arbitrary background decoration.
- Use artwork in marketing, onboarding, empty, and error states; actual execution and evidence views should privilege observed data.
- Keep source-asset license notices with the repository. Do not mix Flowbite Pro or other paid illustrations into this set.
- Validate desktop/mobile layout, both workspace themes, image loading, case provenance, and the browser migration journey in the Firefox acceptance suite.
