# Lesson 4: Agency Deployment — Integrations, Scaling & Client Delivery

> **Level:** Builder (L1)
> **XP Reward:** +350 XP | Running Total: 1,100 XP
> **Duration:** ~1.5 hours
> **Prerequisites:** Lessons 1–3 complete, qualification funnel live
> **Goal:** Connect ManyChat to external tools, build a reusable agency starter kit, understand compliance, and deliver client results professionally.

---

## Module 1: Native Integrations

ManyChat has built-in integrations that connect without Zapier or Make.com. These are the ones worth knowing before reaching for middleware.

### Shopify

For e-commerce clients. Connects ManyChat to the Shopify store and unlocks:

- **Abandoned cart flows:** When a shopper abandons cart, trigger a DM sequence ("You left something behind 👀")
- **Order confirmation DMs:** Send order details in DM instead of (or alongside) email
- **Back-in-stock alerts:** Contact subscribes to alerts → DM when product restocks
- **Post-purchase review requests:** 3 days after delivery → request a review via DM

Integration setup: **Settings → Integrations → Shopify → Connect Store**

### HubSpot

For clients running sales pipelines in HubSpot. Syncs ManyChat contacts bidirectionally:

- New ManyChat subscriber → create HubSpot contact
- ManyChat lead qualified tag set → move HubSpot deal to "Qualified" stage
- HubSpot deal closed → trigger ManyChat onboarding flow

Integration setup: **Settings → Integrations → HubSpot → Connect**

### Google Sheets

The simplest data destination. Every new ManyChat contact (or every qualified lead) logs a row in a spreadsheet.

Useful for:
- Clients who don't have a CRM and just want a lead list
- Reporting to clients (here is your weekly lead count in a sheet they can see)
- Quick setups where you don't need a full CRM

### Mailchimp

Adds new ManyChat subscribers to a Mailchimp audience list. Useful when the client already has an established email list and wants DM + email to run in parallel.

New lead in ManyChat → add to Mailchimp → Mailchimp handles the email nurture sequence.

### Calendly

Two-way: Calendly can trigger webhooks when a booking is made, which ManyChat (via Zapier) can catch and set a tag. ManyChat can also send the Calendly booking link inside a DM.

---

## Module 2: Zapier Integrations (7,000+ Apps)

**Zapier** is the bridge between ManyChat and the rest of the software world. ManyChat → Zapier → anything.

### Setting Up ManyChat → Zapier

In ManyChat: **Settings → Integrations → Zapier → Connect**

This generates a webhook URL and API connection. In Zapier, ManyChat appears as a native app with triggers and actions:

**ManyChat Triggers in Zapier:**
- New subscriber
- Tag added to contact
- Custom field updated
- Contact opted out

**ManyChat Actions in Zapier:**
- Send message to contact
- Add tag to contact
- Set custom field
- Subscribe to sequence

### High-Value Integration Patterns

#### Pattern 1: New Lead → CRM + Email List

```
Trigger: ManyChat tag "qualified-lead" added
    → Zapier action 1: Create contact in HubSpot/Pipedrive
    → Zapier action 2: Add to Mailchimp/ActiveCampaign audience
    → Zapier action 3: Send Slack/email notification to client
```

#### Pattern 2: Stripe Payment → Confirmation DM

```
Trigger: Stripe "Payment Succeeded" event
    → Zapier action 1: Find ManyChat contact by email
    → Zapier action 2: Add tag "paid-customer" in ManyChat
    → Zapier action 3: Send ManyChat message "Your payment went through! Here's your access link: [link]"
```

#### Pattern 3: Appointment Booking → Calendar + Reminder

```
Trigger: Calendly "Invitee Created" event
    → Zapier action 1: Create Google Calendar event
    → Zapier action 2: Set ManyChat field "appointment_time"
    → Zapier action 3: Add ManyChat tag "call-booked"
    (ManyChat flow handles DM reminders from the tag trigger)
```

#### Pattern 4: Lead Qualified → Deal Created in CRM

```
Trigger: ManyChat tag "qualified-lead" added
    → Zapier action 1: Get contact fields (name, budget, challenge, email)
    → Zapier action 2: Create deal in HubSpot/Pipedrive with those fields pre-filled
    → Zapier action 3: Assign deal to sales rep
```

💡 **PRO TIP:** Build Zapier templates reusably. Once you've built "ManyChat → HubSpot new contact" for one client, duplicate the Zap, update the account connections, and it's live for the next client in 5 minutes.

---

## Module 3: Make.com for Advanced Workflows

**Make.com** (formerly Integromat) handles more complex logic than Zapier. Use it when:
- A workflow has more than 3 steps
- You need conditional logic in the middleware
- You're transforming data (reformatting, filtering, aggregating)
- You need error handling and retry logic

### ManyChat + Make.com Pattern

```
[ManyChat contact qualifies]
    → Sends webhook to Make.com with:
        {
          "first_name": "{first name}",
          "email": "{email}",
          "budget": "{budget_range}",
          "challenge": "{main_challenge}",
          "instagram_id": "{subscriber_id}"
        }
    → Make.com receives and:
        1. Creates HubSpot contact
        2. Creates HubSpot deal with stage "New Lead"
        3. Adds contact to ActiveCampaign list "New Leads"
        4. Sends Slack message to client's #leads channel
        5. Logs to Google Sheets "Lead Tracker" tab
        6. Calls ManyChat API to send a personalized follow-up DM
```

This single Make.com scenario replaces what would be 6 separate Zapier zaps — and it handles errors gracefully.

### Make.com Webhook Setup in ManyChat

1. In Make.com: Create a new scenario → add a Webhook trigger → copy the webhook URL
2. In ManyChat: Add Action block → "Send HTTP Request" → paste webhook URL → POST with JSON body containing contact fields

---

## Module 4: ManyChat API for Custom Integrations

The **ManyChat API** lets you interact with ManyChat from external code. Used when you're building custom software for a client or when no-code tools aren't enough.

### Key API Endpoints

```
Base URL: https://api.manychat.com

GET  /fb/subscriber/getInfo?subscriber_id={id}      — get contact data
POST /fb/subscriber/addTag                           — add a tag
POST /fb/subscriber/removeTag                        — remove a tag
POST /fb/subscriber/setCustomFieldByName            — set a custom field
POST /fb/sending/sendContent                        — send a message to a contact
POST /fb/subscriber/createSubscriber               — create a new contact
GET  /fb/page/getTags                               — list all tags
```

### Authentication

All API calls require your ManyChat API key:

```
Header: Authorization: Bearer YOUR_API_KEY
```

Get your API key: **Settings → API → Copy Token**

### Example: Send a Message via API

```python
import requests
import os

api_key = os.environ.get("MANYCHAT_API_KEY")

response = requests.post(
    "https://api.manychat.com/fb/sending/sendContent",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "subscriber_id": "1234567890",
        "data": {
            "version": "v2",
            "content": {
                "messages": [
                    {
                        "type": "text",
                        "text": "Hey! Just following up from our earlier conversation."
                    }
                ]
            }
        }
    }
)

print(response.json())
```

### Example: Set a Custom Field via API

```python
response = requests.post(
    "https://api.manychat.com/fb/subscriber/setCustomFieldByName",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "subscriber_id": "1234567890",
        "field_name": "crm_deal_id",
        "field_value": "DEAL-00123"
    }
)
```

⚠️ **WARNING:** Never hardcode API keys in scripts. Store them in environment variables or a secrets manager. If a client's ManyChat API key is exposed, anyone can send messages to their entire subscriber list.

---

## Module 5: Building Your Agency Starter Kit

Every agency should have a reusable flow template library. When you onboard a new client, you import templates, update the copy, and go live in hours instead of days.

### The 6 Flows Every Client Needs

Build these once, export as templates, reuse across clients:

| Flow | Trigger | Purpose |
|------|---------|---------|
| **Welcome Flow** | New subscriber or Follow trigger | Introduce the brand, set expectations, soft CTA |
| **Lead Magnet Flow** | Comment keyword | Deliver free resource, collect email |
| **Lead Qualification Flow** | DM intent | 3-question funnel → qualified → booking / unqualified → nurture |
| **Appointment Booking Flow** | "BOOK" keyword / qualified-lead tag | Send Calendly link, confirm booking, set reminders |
| **FAQ / Knowledge Base Flow** | Default reply | Handle common questions via AI + Knowledge Base |
| **Reactivation Flow** | Dormant contact (90+ days no engagement) | Re-engage or clean list |

### Exporting Templates

1. Open a flow you want to save as a template
2. Click "..." (More options) → "Share"
3. Copy the share link
4. Save links in your agency's internal doc or Notion with notes on what to customize

### What to Customize Per Client

When importing a template for a new client:

- [ ] Replace all copy with the client's brand voice
- [ ] Update lead magnet links to client's actual resources
- [ ] Swap Calendly links to client's account
- [ ] Update the admin notification email to the client's email
- [ ] Reconnect any Zapier/Make.com integrations to client's accounts
- [ ] Update the Knowledge Base with the client's actual business info
- [ ] Test all flows from a secondary account before go-live

💡 **PRO TIP:** Build a "Client Onboarding Checklist" doc that lists every customization point. When you hand off to a client or bring on a team member, they follow the checklist and nothing gets missed.

---

## Module 6: Compliance — Non-Negotiable Rules

Compliance is where agencies get clients in trouble — or get clients' accounts banned. Know these rules cold.

### Meta's 24-Hour Messaging Window

**The rule:** After a user sends a message to a business on Instagram or Messenger, the business has a **24-hour window** to send non-promotional messages. After 24 hours, you can only send **approved Message Tags** (specific use cases like confirmed appointment reminders, post-purchase updates, account alerts).

**What this means in practice:**
- Promotional follow-ups and sales messages must happen within 24 hours of the user's last message
- If the window closes, you need the user to re-engage (reply to your message) to reopen it
- This is why aggressive follow-up sequences work better in DMs than email — you need to capture the conversation within 24 hours

**Workaround:** Send a non-promotional check-in message ("Did you have any questions about what I sent over?") to keep the window open while you warm up the lead.

### WhatsApp Template Approval

For WhatsApp outbound messages (outside the 24-hour service window), Meta requires pre-approved **Message Templates**.

Templates must:
- Be approved by Meta before use (review takes 1–5 business days)
- Serve a specific, stated purpose (appointment reminder, order update, etc.)
- Not be purely promotional
- Include opt-out language

Never send unapproved outbound WhatsApp messages. The number gets flagged and can be permanently banned.

### SMS Opt-In Requirements (TCPA — US)

If you're running SMS flows for US-based clients:

- Contacts must have given **explicit written consent** to receive automated text messages
- Consent cannot be buried in terms of service — it must be a clear, separate opt-in
- Every SMS must include an opt-out instruction ("Reply STOP to unsubscribe")
- Keep records of consent for every number

💀 **COMMON MISTAKE:** Importing a phone number list into ManyChat SMS without explicit opt-in consent. Even if those contacts gave their phone number on a form, they may not have consented to automated SMS. TCPA violations carry fines up to $1,500 per message.

### General Best Practices

- Always honor opt-out requests immediately (ManyChat handles this automatically for subscribed/unsubscribed status)
- Never send to contacts who have opted out
- Keep promotional messages to 1–2 per week maximum — frequency kills engagement and leads to blocks
- Test every flow for spam-like characteristics before go-live

---

## Module 7: Client Reporting and ROI Tracking

Clients pay for results. Your job is to show them the results clearly and connect them to revenue.

### ManyChat Analytics

Access via **Analytics** in the left sidebar. Key metrics:

| Metric | What It Tells You |
|--------|------------------|
| **New Subscribers** | List growth rate |
| **Flow Open Rate** | What % of contacts opened a specific flow |
| **Flow Click Rate** | What % clicked a button or link |
| **Unsubscribe Rate** | Flows or messages that are pushing people away |
| **Live Chat Volume** | How often humans are needed |
| **Broadcast Performance** | Open/click rate on sent broadcasts |

### Building a Client Report

Deliver this monthly. Keep it to one page:

```
## ManyChat Report — [Client Name] — [Month]

### Growth
- New subscribers this month: [N]
- Total subscriber count: [N]
- Month-over-month change: +/- [N]%

### Top Performing Flows
| Flow | Contacts Entered | Open Rate | Click Rate |
|------|-----------------|-----------|-----------|
| Lead Magnet — Comment GUIDE | [N] | [X]% | [X]% |
| Lead Qualification | [N] | [X]% | [X]% |

### Leads Generated
- Total contacts who reached "qualified-lead" tag: [N]
- Appointments booked via ManyChat booking flow: [N]
- Estimated value (appointments × avg deal size): $[X]

### Actions This Month
- [Flow launched/updated/optimized — 1 sentence per action]

### Next Month Plan
- [1–2 improvements planned]
```

💡 **PRO TIP:** Connect ManyChat lead data to the client's actual revenue data whenever possible. "We sent 47 qualified leads to your booking link. You closed 8 deals at $2,000 average. That's $16,000 in revenue from this channel." That conversation is why retainers renew.

---

## Module 8: Cost Optimization

Keeping client ManyChat accounts clean and cost-effective is part of the service.

### Auto-Unsubscribe Dormant Contacts

ManyChat Pro pricing scales with contact count. Contacts who haven't engaged in 90+ days inflate the bill without generating value.

Build a maintenance flow:

```
[Scheduled Trigger: runs weekly]
    → [Condition: last interaction > 90 days AND tag "dormant" not set]
        YES → [Set tag "dormant"]
             → [Send reactivation message: "Hey {first name}! Just checking in — still interested in [topic]? Reply YES to stay in the loop, or no action needed to unsubscribe."]
             → [Delay: 7 days]
             → [Condition: replied in last 7 days?]
                  YES → [Remove tag "dormant"]
                  NO  → [Unsubscribe from all — removes from paid contact count]
```

This keeps the subscriber count accurate and the billing predictable.

### Monitoring Contact Count vs. Plan Tier

Set a calendar reminder to review contact count monthly against the Pro pricing tiers. If a client is at 4,800 contacts and the next tier ($65/mo) kicks in at 5,000, decide:
- Is the growth trajectory worth the tier jump?
- Should you run a list clean before crossing the threshold?

---

## Module 9: Agency Pricing and Positioning

### How to Price ManyChat Services

**Setup fee (one-time):** Covers flow building, account configuration, integration setup, testing

| Scope | Typical Range |
|-------|--------------|
| Single flow (lead magnet or FAQ bot) | $300–$600 |
| Full starter kit (3–4 flows, 1 integration) | $800–$1,500 |
| Enterprise setup (6+ flows, CRM integration, multi-channel) | $2,000–$4,000 |

**Monthly retainer:** Covers ongoing management, optimization, new campaign flows, reporting

| Scope | Typical Range |
|-------|--------------|
| Light maintenance (monthly report, 1 flow update) | $200–$400/mo |
| Active management (new campaigns, A/B testing, weekly optimization) | $500–$900/mo |
| Full-service (multi-client-facing, dedicated support to client's team) | $1,000+/mo |

**ManyChat Pro subscription:** Pass through at cost or mark up slightly. Transparency is better — tell clients exactly what ManyChat costs and what your fee is on top.

### Who to Pitch

ManyChat works best for clients who:
1. Post actively on Instagram (reels, stories) — the more they post, the more the comment triggers fire
2. Have a service with a clear lead-to-booking flow (gyms, salons, dentists, coaches, real estate, e-commerce)
3. Currently have a DM inbox that is overwhelmed or unanswered
4. Are running paid Instagram ads (comment triggers dramatically increase ad ROI)

---

## Module 10: Common Agency Mistakes

These are the failure modes that burn clients and kill retainers.

💀 **COMMON MISTAKE 1: Over-automating to the point of feeling robotic.** Not every interaction needs a bot. When a lead is warm and ready to buy, routing them through another 5-question qualification flow is the wrong move. Build in natural human handoff points and trust them.

💀 **COMMON MISTAKE 2: No human handoff at all.** Building a fully automated funnel and never checking the Live Chat inbox. Leads ask questions the bot can't answer. Without a human monitoring Live Chat, those leads die silently. Someone must own the inbox.

💀 **COMMON MISTAKE 3: Ignoring the 24-hour rule.** Building aggressive 7-day DM sequences and wondering why engagement drops to zero after day 1. The window closes. Understand the rule and design flows around it.

💀 **COMMON MISTAKE 4: Generic messages.** Using "Hey friend! Thanks for connecting!" type language across all clients. Every message should sound like it came from that specific brand. Personalization is not just first names — it's brand voice, offer specificity, and relevant context.

💀 **COMMON MISTAKE 5: Not testing before go-live.** Launching a client flow without testing every branch from a secondary account. Found a broken path? The client's audience finds it first.

🧠 **KEY TAKEAWAY:** The agency's job is not just to build flows — it is to build flows that produce measurable business outcomes. A beautiful flow that doesn't generate qualified leads is a failed deployment. Always define success metrics before building.

---

## Exercise: Connect ManyChat to a CRM via Zapier + Build Your Starter Kit

**Deliverable:** A working Zapier integration connecting ManyChat to a CRM, plus 3 saved flow templates in your agency starter kit.

**Step 1: Set up the Zapier integration**

1. Create a free Zapier account (zapier.com)
2. Create a new Zap: Trigger = ManyChat "Tag Added" → filter for tag = "qualified-lead"
3. Action = create a contact in HubSpot (or Google Sheets if no CRM yet)
4. Map fields: first_name, email, budget_range, main_challenge
5. Turn the Zap on
6. Test: add the "qualified-lead" tag to a test contact in ManyChat → verify the row appears in HubSpot/Sheets

**Step 2: Build your starter kit**

Export 3 flows as share links and document them:

```markdown
## Agency Starter Kit — ManyChat Templates

### 1. Lead Magnet — Comment Trigger
Link: [your share link]
Customize: keyword, lead magnet link, email follow-up copy

### 2. Lead Qualification Funnel
Link: [your share link]
Customize: qualifying questions, budget options, Calendly link, admin notification email

### 3. FAQ Bot — Default Reply
Link: [your share link]
Customize: Knowledge Base sources (client's website URL), fallback message, human handoff
```

**Step 3:** Post your starter kit doc in the community. Explain what each template does in one sentence.

---

## Checklist Before Calling This Course Complete

- [ ] Know ManyChat's 5 native integrations (Shopify, HubSpot, Sheets, Mailchimp, Calendly)
- [ ] Built at least one Zapier integration (ManyChat → external tool)
- [ ] Understand the hybrid architecture: ManyChat + Make.com + external AI
- [ ] Know the ManyChat API authentication pattern and 3 key endpoints
- [ ] Have a 6-flow agency starter kit with reusable templates
- [ ] Know Meta's 24-hour messaging window rule
- [ ] Know WhatsApp template approval requirements
- [ ] Know TCPA SMS opt-in requirements
- [ ] Can build a client report from ManyChat Analytics
- [ ] Know how to keep contact counts clean (dormant unsubscribe flow)
- [ ] Have a pricing framework for setup + retainer
- [ ] Know the 5 common agency mistakes — and how to avoid them

**All boxes checked?** You can deploy ManyChat for any service business client, connect it to their existing tools, and deliver measurable results. This is a deployable agency service.

---

🏆 **BOSS LEVEL:** Take a real (or hypothetical) service business client and build their complete ManyChat stack: welcome flow, lead magnet flow, qualification funnel, booking flow, FAQ bot, and CRM integration via Zapier. Document it as a case study. Post it in the community. This is your proof of work.

---

**Course Complete — 1,100 XP Earned**

You have gone from zero ManyChat knowledge to a full agency deployment capability. The next step is to land a client and bill for it.

**Next up:** Use the lead qualification flow you built in this course to generate your first ManyChat client. The tool that gets you clients is the same tool you're selling. Deploy it for yourself first.
