-- 085_user_profiles_personal_phone.sql
--
-- SunBiz product decision #6 (Option A from TOMORROW.md): personal
-- phone is stored on user_profiles as display data, NOT used for
-- outbound routing. Outbound SMS still goes through the shared
-- tenant Twilio number. The personal field lets agents say "you can
-- reach Alex on her cell at 555-1234" and lets dashboards show
-- per-user contact info.
--
-- Phase B (true per-employee Twilio sub-accounts) would require a
-- separate twilio_user_credentials table; deferred until volume
-- justifies the per-line spend.

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS personal_phone text;

COMMENT ON COLUMN public.user_profiles.personal_phone IS
  'Operator personal cell or DID. Display-only; outbound SMS still '
  'uses the shared tenant Twilio. Updated by the operator via Settings. '
  'No validation enforced at the column level — application normalises.';
