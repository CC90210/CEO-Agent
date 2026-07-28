---
tags: [template, email, invoice, finance]
name: Invoice Reminder Sequence
type: email_sequence
use_case: Following up on unpaid invoices from active or past clients
variables: [client_name, invoice_number, amount, due_date, payment_link, service_description]
last_updated: 2026-04-27
---

# Invoice Reminder Sequence

## Tone Calibration

This sequence escalates gradually. The goal is payment, not confrontation. Assume the first few missed payments are oversight — most clients are not intentionally withholding. The tone shifts from friendly reminder to professional firmness, ending with a clear consequence at Day 30.

Never apologize for requesting payment. You delivered the work. Payment is the agreed exchange.

---

## Day 0 — Due Date Reminder (Proactive)

**Trigger:** Send this 1 day before or on the due date. Proactive contact reduces lateness.

**Subject:** Invoice #{{invoice_number}} due [today / tomorrow]

Hi {{client_name}},

Quick note that invoice #{{invoice_number}} for {{amount}} is due [today / tomorrow].

**Payment link:** {{payment_link}}

If you have any questions about the invoice or the work covered, happy to sort it out quickly.

Best,
Conaugh

---

## Day 7 — First Overdue Notice

**Trigger:** 7 days after the original due date, no payment received.

**Subject:** Invoice #{{invoice_number}} — 7 days past due

Hi {{client_name}},

Following up on invoice #{{invoice_number}} for {{amount}}, which was due on {{due_date}}.

If payment is already in transit, please disregard — and let me know so I can confirm receipt on my end.

If not, here is the payment link: {{payment_link}}

Happy to answer any questions about the invoice if there is an issue.

Best,
Conaugh McKenna
OASIS AI Solutions

---

**Notes:** Friendly and non-accusatory. "If payment is already in transit" gives them a graceful out and reduces defensiveness. Short and easy to action.

---

## Day 14 — Second Notice

**Trigger:** 14 days past due, no payment or response.

**Subject:** Invoice #{{invoice_number}} — following up (14 days overdue)

Hi {{client_name}},

I am following up on invoice #{{invoice_number}} for {{amount}}, now 14 days past the due date of {{due_date}}.

I want to make sure there is no issue on my end — sometimes invoices get lost in inboxes or there is a question about a line item that holds things up.

Can you let me know the expected payment timeline, or flag any questions about the invoice?

Payment link: {{payment_link}}

Thanks,
Conaugh

---

**Notes:** The "is there an issue on my end?" framing is deliberate — it gives the client a low-friction reason to respond and surfaces any billing disputes early, before they become relationship problems.

---

## Day 21 — Firm Notice

**Trigger:** 21 days past due, no payment or meaningful response.

**Subject:** Invoice #{{invoice_number}} — action required

Hi {{client_name}},

Invoice #{{invoice_number}} for {{amount}} ({{service_description}}) is now 21 days overdue from the original due date of {{due_date}}.

I need to resolve this within the next 7 days. Please process payment at the link below or reply to discuss a payment arrangement:

**Payment link:** {{payment_link}}

If there is a dispute about the work or the invoice amount, please respond today so we can address it directly.

Thank you,
Conaugh McKenna
Founder, OASIS AI Solutions

---

**Notes:** Tone is now firm but still professional. "Reply to discuss a payment arrangement" opens the door to partial payments or short extensions — which is better than silence. The 7-day window creates urgency without being threatening. Full name and title reinforce the formality.

---

## Day 30 — Final Notice

**Trigger:** 30 days past due, no payment or agreement in place.

**Subject:** FINAL NOTICE — Invoice #{{invoice_number}} — {{amount}} overdue

Hi {{client_name}},

This is a final notice regarding invoice #{{invoice_number}} for {{amount}}, now 30 days overdue (original due date: {{due_date}}).

If payment is not received or a payment arrangement is not agreed upon within 5 business days, I will be taking the following steps:

1. Pausing all active services on your account
2. Referring the outstanding balance to collections

I do not want to take either of those steps, and I hope we can resolve this today.

**Payment link:** {{payment_link}}

If you are experiencing a genuine hardship, please contact me directly and we will work something out.

Conaugh McKenna
Founder, OASIS AI Solutions
[Phone number]

---

**Notes:** Consequences must be stated clearly and followed through on. Vague threats reduce your credibility. The "genuine hardship" line keeps the relationship door open — some clients go quiet because they are embarrassed, not malicious. Giving them a direct phone number at this stage signals you are willing to resolve it.

---

## Escalation Decision Tree

```
Day 30 passes with no response
    ↓
Is this a retainer client (ongoing relationship)?
    YES → One phone call before collections. State consequences verbally.
    NO  → Move directly to collections or small claims

Is the amount > $1,000?
    YES → Use a collections service or formal demand letter
    NO  → Small claims court (Ontario: claims up to $35,000)

Did they do work that is partially usable but disputed?
    YES → Offer partial credit in exchange for final settlement amount
    NO  → Full amount owing, no discount
```

---

## Obsidian Links
- [[brain/STATE]] | [[brain/USER]]
- [[data/templates/documents/project-brief]] | [[data/templates/documents/status-report]]
