# Customer Onboarding — Verbatim Phone Script

**Audience:** OASIS operator (you, CC).
**When to use:** First call with a new SunBiz client after they've signed the agreement and before you run the Bootstrap step.
**Length:** 12–18 minutes if read straight; expect 20–25 with their questions.

This is the verbatim script. Read it. Don't paraphrase. Once you've run it three times you can deviate, but the words below are tested for compliance (TCPA + SOC 2 posture) and conversion (low-friction sign-off).

---

## 1. Opening + scope confirmation (90 seconds)

> "Hey [first name], it's [your name] from OASIS — got a minute to walk through what's about to happen on your end?
>
> Quick recap so we're aligned: you signed up for **Solara**, the funding-ops agent. It runs day-to-day operations for [their company] — lead intake, SMS follow-up, application routing, offer tracking, funded-deal lifecycle, and renewal triage. You'll see all of that in a dashboard we're about to set up on your Mac Mini.
>
> Three things I'm going to do on this call:
>
> 1. Walk through the data-sovereignty choice. Spoiler — we recommend Local for funding ops, and I'll explain why.
> 2. Get you signed into your dashboard and paired with your machine.
> 3. Show you the agent answering one real question so you know it works.
>
> Cool to go?"

**Wait for explicit yes.** If they hesitate, pause and ask what's on their mind before moving on.

---

## 2. Data sovereignty explanation (3 minutes)

> "First decision, and it's the only one that actually matters today: **where does your loan-file data live?**
>
> You've got two options. I'll explain both in plain English, then we'll pick.
>
> **Option 1 — Local.** Your loan data, applications, lender offers, commissions — all of it sits in a file on the Mac Mini in your office. Not on a server we manage. Not on a cloud database. A literal file on your hardware. If our entire company disappears tomorrow, your data is still on your machine and you can keep operating.
>
> The OASIS dashboard reads what's called a *pulse* — basically a heartbeat that tells us your agent is alive and how it's performing — but we can't read your actual loan data. That's by design.
>
> **Option 2 — Cloud.** We host the database in a managed Supabase instance. Faster initial setup, automatic backups, but your data lives on a server we operate. Other tenants are isolated by row-level security so they can't see yours.
>
> For funding ops, especially with merchant tax IDs and bank-statement uploads, we strongly recommend **Local**. The compliance posture is cleaner — if a merchant's lawyer ever asks where their data is, the answer is 'on the broker's premises,' not 'on a third-party cloud.'
>
> Any reason you'd want Cloud instead of Local?"

**Listen for objections:**
- "What if my Mac Mini crashes?" → "Same as any office computer: nightly Time Machine backup, you're covered. The dashboard will tell you within 15 minutes if the bridge goes offline."
- "Can I switch later?" → "Yes, we can migrate Local→Cloud or back. It's a one-time SQL export-import."

**Make the choice in real time.** Don't leave it for later.

---

## 3. SMS opt-in language (90 seconds)

> "One quick compliance note while I have you: Solara sends SMS to your leads — that's the core of your follow-up workflow. We need you to confirm two things on the record:
>
> 1. Every contact in your CRM has given prior express written consent to receive SMS messages from your business. **Yes or no?**
> 2. Every outbound SMS will include the words 'Reply STOP to unsubscribe' on first message. That's hard-coded in the templates — we cannot turn it off. **OK with that?**
>
> Great. If either of those changes — for example you import a list from another broker — call me before you blast. The agent will refuse to send to contacts marked as unverified consent."

**Document their yes/yes in your call notes.** If they say no to either, halt the onboarding and route to legal.

---

## 4. Sign-in + dashboard pairing (4 minutes)

> "Now the technical bit. Two-step process. I'll talk you through it.
>
> **Step one:** Open your browser, go to [dashboard URL]. Sign in with the email you used on the agreement. You should land on a page that says 'Operations Command' with the Sun Biz Funding header.
>
> See it? Good.
>
> **Step two:** On the Mac Mini, open Terminal and type `bravo setup --profile=sunbiz`. The wizard will ask you a few questions — answer naturally — and at one point it will auto-open the same dashboard page in your browser to a Devices screen. Click the button that says 'Install Claude Code CLI bridge'. You'll see a 9-character code, three groups of three letters. Type that into Terminal when the wizard prompts you. The wizard handles the rest.
>
> When you see 'Bridge token saved' in green, you're paired. Refresh the dashboard. You should see your name in the top-right and Solara listed as online.
>
> All set?"

**Stay on the call through this step.** Watch them paste the code. Note any error messages verbatim — they'll fall into one of three buckets (expired code, wrong format, network) and you'll learn to recognize each.

---

## 5. Solara handoff demo (2 minutes)

> "Quick demo so you know it's working. Click the 'Agents' tab in your sidebar. You should see Solara, gold sun icon.
>
> Type this exact question: **'Show me the leads you'd contact today and tell me why.'**
>
> [Wait for response, ~15-20 seconds]
>
> Read the response with me. Solara should be naming specific leads from your CRM, ranking them by some combination of recency, status, and renewal proximity, and explaining the call-order. If it's vague — 'I would prioritize the most promising leads' — call me back; we need to debug your data import.
>
> Otherwise: that's your morning routine. Every weekday at 8am you'll pull this up, eyeball the list, run the calls."

---

## 6. Expectation setting (2 minutes)

> "Three things to set straight before we wrap:
>
> 1. **Response time.** Solara replies within 10 seconds for chat questions. SMS follow-ups go out within 90 seconds of a lead being marked qualified. If you ever wait more than 5 minutes for either, something's wrong — text me directly.
>
> 2. **What it won't do.** Solara will not initiate cold outreach to leads it hasn't been told about. It will not modify pricing on offers without your approval. It will not send to opted-out contacts even if you ask it to.
>
> 3. **Your job in week one.** Run the morning lead review. Watch what Solara recommends. Correct it when it's wrong — say 'no, the Tucson account isn't ready, push to next week' and it will learn. The agent gets sharper the more you correct it; week-one corrections compound for months.
>
> Make sense?"

---

## 7. Sign-off (60 seconds)

> "Last thing: you've got my number. The agent does most of the work, but if you ever feel like the dashboard is lying to you, or you want a deal opinion from a human, text me. Don't wait until Friday — small fires now beat big fires later.
>
> Welcome aboard. Talk soon."

**End the call. Don't linger.** Send the follow-up email within 10 minutes containing:
- Confirmation of their Local/Cloud choice
- Confirmation of their SMS consent attestation
- Direct phone for emergencies
- Link to the [SunBiz runbook](/playbook/06-sunbiz-runbook) for self-service questions

---

## After the call — operator checklist

- [ ] Call notes filed: data choice, SMS attestation Y/Y, paired-at timestamp
- [ ] Their `tenant.brand` reads "Sun Biz Funding" and `tenants.custom_fields.command_center_profile_slug = "sun"`
- [ ] Solara heartbeat green in their state DB
- [ ] First-week check-in scheduled in your calendar (5 business days out)
- [ ] Logged a quest in your ACTIVE_TASKS.md to review their first-week corrections on day 7
