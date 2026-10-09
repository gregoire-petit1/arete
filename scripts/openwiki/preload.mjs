import { createTransport } from './transport.mjs';

// The pinned ChatOpenRouter client uses global fetch. Preload before OpenWiki
// installs its diagnostic wrapper so every provider attempt obeys our limits.
globalThis.fetch = createTransport({ fetch: globalThis.fetch });
