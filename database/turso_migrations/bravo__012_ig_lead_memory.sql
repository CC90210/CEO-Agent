-- bravo__012 — give the Instagram setter a memory of the LEAD, not just of the log.
--
-- Before this, everything the agent "knew" about a person was six atomic
-- extracted_* fields plus whatever Zernio still held in the thread. Two holes
-- follow from that, and both of them read to a prospect as "nobody here
-- remembers me":
--
-- 1. THE HEAD IS THE PART THAT FALLS OFF. build_transcript keeps the newest
--    MAX_TRANSCRIPT_TURNS (40) turns and _fetch_thread only asks for the newest
--    60 raw messages. The turns that scroll out first are the OPENING ones — the
--    business, the problem, the timing, the price objection, the thing we already
--    offered. Exactly the qualifying context. On the longest, warmest, closest to
--    closing conversation this account has ever had, the agent's memory of how
--    the deal started is the first thing it loses.
--
-- 2. WHAT WAS DISCUSSED WAS NEVER STORED AT ALL. No column and no prompt slot
--    for a budget signal, an objection the prospect raised, or what we have
--    already pitched. `last_decision_json` is written on every reply and read by
--    nothing, so re-deriving the sales state from the raw chat log was the only
--    option — and for a dormant thread Zernio returns `messages: []`, so there
--    was nothing to derive from.
--
-- Four nullable TEXT columns. They are refreshed on EVERY successful turn, not
-- at truncation time: a recap written at the moment the head is dropped would be
-- written from a window that no longer contains the thing it has to summarise.
-- By the time turn 41 pushes turn 1 out, the recap already covers turn 1.
--
-- PROVENANCE, because storage does not launder it: every value in here is the
-- stranger's own words, or a model's paraphrase of them. It is exactly as
-- untrusted as the transcript and it is rendered inside its own
-- <<<UNTRUSTED_LEAD_MEMORY_*>>> fence, never inside the trusted state block.
-- ig_dm_state.apply_memory sanitises and caps on the way IN as well, so a stored
-- note cannot grow without bound and cannot carry a control character or a
-- forged fence into the next prompt.
--
-- Nullable with no default on purpose: NULL means "we have not learned this
-- yet", which is the honest state of all 26 live rows the moment this lands. A
-- '' default would make "unknown" and "they told us nothing" the same value.

ALTER TABLE instagram_dm_conversations ADD COLUMN memory_budget TEXT;
ALTER TABLE instagram_dm_conversations ADD COLUMN memory_objections TEXT;
ALTER TABLE instagram_dm_conversations ADD COLUMN memory_pitched TEXT;
ALTER TABLE instagram_dm_conversations ADD COLUMN memory_summary TEXT;
