"""Named execution envelope, independent of the framework."""

MAX_TOOL_CONCURRENCY = 4
MAX_RUN_SECONDS = 300
#: Bound free-tier requests, reserving the last call for a tool-free answer.
MAX_MODEL_CALLS = 24
MAX_MODEL_FALLBACKS = 2
MAX_TOOL_CALLS = 96
MAX_READ_TOOL_RETRIES = 1
READ_TOOL_RETRY_DELAY_SECONDS = 0.25
# Framework steps include limit hooks, not just model/tool turns.
MAX_GRAPH_STEPS = 200

MAX_TOOL_OUTPUT_CHARS = 32_000
