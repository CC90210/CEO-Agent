-- bravo__010 — give a booked Instagram DM meeting an inverse.
--
-- events.insert runs with sendUpdates:"all", so creating the calendar event
-- mails a stranger an invite. That is the only irreversible outward act in the
-- whole DM pipeline. google_tool can undo it (`calendar delete <event_id>`,
-- which also mails the cancellation) — but only while somebody still holds the
-- id, and nothing persisted it. A meeting on CC's calendar that no code can
-- find is a trapdoor: easy to enter, no way back.
--
-- Nullable on purpose. Rows booked before this column existed genuinely have no
-- id, and a NOT NULL default would invent one — a fake id is worse than an
-- honest NULL, because it would make `calendar delete` fail against a real
-- event while reporting that a cancel was attempted.
--
-- The legacy static-room path does not print an Event-Id line either, so NULL
-- also legitimately means "booked through the old shared-room path".

ALTER TABLE instagram_dm_conversations ADD COLUMN booked_event_id TEXT;
