# Arete identity

`arete-laurel.svg` is the approved Figma vector, component `163:6005` in
[Arete — Athlete RPG](https://www.figma.com/design/gzX3POjHbPbtjw8I1Nz8Vj?node-id=163-6005).
Use `AreteMark` or `AretePresence` for the application and the AI coach, including
settings, briefings and navigation. Only the separate waiting orbit rotates;
SSE events own the coach waiting state.

The wordmark uses Cormorant Garamond SemiBold, locally hosted under the SIL
Open Font License (see `../fonts/CormorantGaramond-LICENSE.txt`). The WOFF2
subset covers Latin, Latin Extended, French accents and punctuation.
Pierre and Prune reuse the existing semantic colors rather than introduce a
second component or chart theme system. Saved legacy themes remain valid.

## GitHub

The repository README uses the laurel alone, with no embedded wordmark. Its
`<picture>` sources follow GitHub's light/dark theme support and use relative
paths so previews keep the assets from their own branch.

- [Light-background SVG](arete-laurel.svg): Pierre ink, `#1C2927`.
- [Dark-background SVG](arete-laurel-dark.svg): Prune cream, `#F2E8DA`.

The dark-background export has exactly the same geometry as the approved source;
only its fill changes. Keep both paths in sync when updating the source logo.
Both files are transparent vectors with no external fonts or resources.
