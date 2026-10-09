"""Named execution envelope, independent of the framework."""

MAX_TOOL_CONCURRENCY = 4
MAX_RUN_SECONDS = 300
#: A runaway turn must not burn a sixth of a 50-request free daily quota.
MAX_MODEL_CALLS = 8
MAX_TOOL_CALLS = 32
# Framework steps include limit hooks, not just model/tool turns.
MAX_GRAPH_STEPS = 100

MAX_TOOL_OUTPUT_CHARS = 32_000
