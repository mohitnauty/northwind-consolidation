# AI tool transcripts

`claude-code-session.jsonl` is the raw, unedited Claude Code session transcript
for this entire build - from reading the assignment PDF and the data bundle,
through planning, writing every module, running and fixing the pipeline, to
writing these docs. Nothing has been tidied up or removed except one personal
email address (redacted to `[redacted-personal-email]`, 3 occurrences, all in
system-injected context rather than conversation content).

It's a raw JSONL event log (the same format Claude Code's own history uses),
not a prose write-up - it includes tool calls, their full output, and the
dead ends along the way (e.g. the sign-error bug in the intercompany
elimination, the missed duplicate-journal check in the first pass of
`adjustments.py`, the mapping error only caught by an independent hand
calculation not matching). Those are left in deliberately, per the brief's
instruction not to tidy up mistakes.
