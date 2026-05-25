-- 068_shop_out_sender_claim_state.sql
-- Purpose: Support atomic Shop Out sender claims and stop storing local
-- lead_interactions ids in gmail_thread_id.

ALTER TABLE public.application_lender_threads
  DROP CONSTRAINT IF EXISTS application_lender_threads_status_check;

ALTER TABLE public.application_lender_threads
  ADD CONSTRAINT application_lender_threads_status_check
  CHECK (status IN ('pending', 'sending', 'sent', 'replied', 'offer_received', 'declined', 'error'));

ALTER TABLE public.application_lender_threads
  ADD COLUMN IF NOT EXISTS send_interaction_id text;

CREATE INDEX IF NOT EXISTS idx_application_lender_threads_send_interaction_id
  ON public.application_lender_threads(send_interaction_id)
  WHERE send_interaction_id IS NOT NULL;

COMMENT ON COLUMN public.application_lender_threads.status IS
  'Shop-out lifecycle. pending rows are atomically claimed as sending before SMTP, then moved to sent/error/replied/etc.';

COMMENT ON COLUMN public.application_lender_threads.send_interaction_id IS
  'lead_interactions.id returned by send_gateway for the SMTP send; gmail_thread_id is reserved for a real Gmail thread id only.';
