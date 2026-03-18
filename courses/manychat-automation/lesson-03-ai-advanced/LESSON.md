# Lesson 3: Advanced Flows — AI Integration, Lead Qualification & Multi-Channel

> **Level:** Builder (L1)
> **XP Reward:** +300 XP | Running Total: 750 XP
> **Duration:** ~1.5 hours
> **Prerequisites:** Lessons 1 and 2 complete, lead magnet flow live
> **Goal:** Add AI to your flows, build a multi-question lead qualification funnel, and set up a multi-channel nurture sequence.

---

## Module 1: ManyChat AI Add-on Overview

ManyChat's **AI Add-on** is a $29/month upgrade on top of Pro. It adds five AI-powered capabilities that change how your flows work — shifting from rigid keyword matching to intent-based conversation.

| Feature | What It Does | Value |
|---------|-------------|-------|
| **AI Step** | Generates human-like responses based on a goal + context | Handles open-ended questions without rigid scripting |
| **Intention Recognition** | Understands what a contact means, not just what they typed | Removes the "sorry I didn't understand" dead ends |
| **Knowledge Base** | Feed your business info → AI answers from it | Instant 24/7 FAQ bot without manual scripting |
| **Text Improver** | Rewrites your messages to sound more natural | Reduces stilted bot-speak |
| **Flow Builder Assistant** | Describes a flow in plain text → AI builds it | Speeds up flow creation |

To enable: **Settings → Add-ons → AI Add-on → Enable ($29/mo)**

---

## Module 2: AI Step

The **AI Step** replaces the need to script every possible reply. Instead of building a rigid decision tree for "what if they say X," you define a goal and give the AI context — it handles the conversation.

### How to Add an AI Step

1. In the Flow Builder, click "+" to add a node
2. Select "AI Step"
3. Configure:
   - **Goal:** What should the AI accomplish? (e.g., "Qualify the lead and collect their name, budget, and main business challenge")
   - **Context:** Business information for the AI to reference (e.g., "We are a digital marketing agency that helps e-commerce brands grow. Our main offer is a $1,500/mo ads management retainer.")
   - **Max replies:** How many back-and-forth exchanges before the AI either succeeds or escalates (recommend 4–6)
   - **On success:** What happens when the goal is achieved (send to booking flow, set tags, notify admin)
   - **On escalate:** What happens if the AI can't complete the goal (route to human)

### Example AI Step Configuration

```
Goal: Collect the contact's first name, biggest business challenge, and monthly marketing budget.

Context: We are a social media automation agency. We help local service businesses (gyms, salons, dentists, real estate agents) get more leads from Instagram using ManyChat automations. Our entry-level service is a $500 setup fee + $300/month retainer.

Max replies: 5

On success: Set tag "ai-qualified", go to booking flow
On escalate: Set tag "needs-human", convert to Live Chat
```

The AI will ask natural follow-up questions until it has collected all three data points or exhausts the max replies.

💡 **PRO TIP:** Keep the goal specific and bounded. "Collect 3 pieces of information" is a good goal. "Have a conversation and determine if they are a fit" is too vague and will produce inconsistent results. The tighter the goal, the more reliably the AI Step performs.

---

## Module 3: Intention Recognition

**Intention Recognition** replaces keyword triggers with intent-based triggers. Instead of matching the exact word "GUIDE," it understands what the person meant.

### Why Rigid Keywords Fail

A keyword trigger for "BOOK" will miss:
- "booking"
- "Book a call"
- "I want to book"
- "booK" (capitalization)
- "bookie" (accidental)
- "Let's book something"

Intention Recognition handles all of these.

### Setting Up Intention Recognition

1. In your trigger, select "Intention Recognition" instead of "Keyword"
2. Write 3–5 example phrases that express the intent:
   - "book a call"
   - "I want to schedule"
   - "when can we talk"
   - "set up a meeting"
   - "let's connect"
3. Set a confidence threshold (recommend 80%+)
4. ManyChat's AI matches incoming messages to the intent, even with typos and variations

### Intentions vs. Keywords — When to Use Each

| Use Case | Best Choice |
|----------|------------|
| Campaign with specific trigger word ("Comment GUIDE") | Keyword — you need the exact word for algorithmic reasons |
| General DM reply handling | Intention Recognition — people phrase things differently |
| Default reply routing | Intention Recognition — categorize "I want to buy", "I have a complaint", "I want to book" |
| WhatsApp flows | Intention Recognition — WhatsApp conversations are less structured |

---

## Module 4: Knowledge Base

The **Knowledge Base** lets you feed ManyChat your business information — and then the AI uses it to answer questions from contacts.

### What You Can Feed It

- Website URLs (ManyChat scrapes and ingests the content)
- Plain text (paste FAQs, pricing, service descriptions, policies)
- Up to 250,000 characters per entry

### Setting Up a Knowledge Base

1. Go to **Settings → AI → Knowledge Base**
2. Click "New Source"
3. Choose URL or Text
4. For URL: paste your website, service page, or FAQ page
5. For Text: paste your information directly
6. Click "Train" — takes 30–120 seconds

### Using Knowledge Base in Flows

In any Message block, toggle "Use Knowledge Base to answer." When the contact sends a message that matches your trained data, the AI responds from the Knowledge Base instead of the scripted message.

Best used in:
- Default Reply (catches all unmatched messages and answers from your KB)
- AI Step context (the AI references KB when answering follow-up questions)
- A dedicated FAQ flow

```
[Trigger: Default Reply]
    → [Message: Use Knowledge Base enabled]
         → "Thanks for reaching out! {AI answer from Knowledge Base}"
         → [If Knowledge Base has no answer → fallback message → route to human]
```

💀 **COMMON MISTAKE:** Training the Knowledge Base with one URL and expecting it to know everything. If your pricing is on a separate page from your services, train both. If you have a FAQ doc, train that too. The AI only knows what you fed it.

---

## Module 5: ChatGPT / OpenAI Integration

For flows that need more intelligence than ManyChat's built-in AI, you can connect directly to OpenAI's API.

### Two Integration Methods

**Method 1: Native ManyChat AI Step (recommended for most cases)**

Uses ManyChat's AI under the hood. Simpler setup, no API key management, included in the $29 AI add-on.

**Method 2: OpenAI API via Action Block (for custom logic)**

You call OpenAI's API directly from ManyChat using an HTTP Request action. This lets you:
- Use GPT-4o or Claude (via Anthropic API) for more capable responses
- Send structured data (contact fields, conversation history) to OpenAI
- Get structured JSON responses back and save to custom fields

### Setting Up OpenAI via Action Block

```
1. Get OpenAI API key: platform.openai.com → API Keys → Create new key
2. In ManyChat Flow: Add Action → "Send HTTP Request"
3. Configure:
   URL: https://api.openai.com/v1/chat/completions
   Method: POST
   Headers:
     Authorization: Bearer YOUR_API_KEY
     Content-Type: application/json
   Body:
     {
       "model": "gpt-4o-mini",
       "messages": [
         {
           "role": "system",
           "content": "You are a helpful assistant for [Client Name]. Answer questions about their services."
         },
         {
           "role": "user",
           "content": "{{last_input_text}}"
         }
       ],
       "max_tokens": 300
     }
4. Save response to custom field: "ai_response"
5. Next Message block: send {ai_response} to the contact
```

⚠️ **WARNING:** OpenAI API calls add latency (1–3 seconds). For real-time DM conversations, this is acceptable. For time-sensitive contexts (like appointment reminders), use ManyChat's native features instead.

---

## Module 6: Hybrid Architecture — ManyChat + Make.com + External AI

For agency clients with complex automation needs, the most powerful architecture is:

```
ManyChat (frontend)
    → Sends contact data via webhook to Make.com
        → Make.com orchestrates:
            - OpenAI/Claude API call (generates response)
            - CRM update (HubSpot, Pipedrive)
            - Google Sheets logging
            - Email trigger (Mailchimp/ActiveCampaign)
        → Make.com sends response back to ManyChat via API
    → ManyChat delivers the response to the contact
```

### When to Use the Hybrid Architecture

| Use Case | Recommended Approach |
|----------|---------------------|
| Simple FAQ bot | ManyChat AI Step + Knowledge Base |
| Lead magnet delivery + email collection | Native ManyChat flows |
| Complex qualification + CRM sync | ManyChat + Zapier/Make.com |
| Custom AI persona with your client's brand voice | ManyChat + Make.com + OpenAI |
| Multi-channel with advanced logic | Full hybrid stack |

The hybrid approach adds complexity. Only use it when native ManyChat capabilities genuinely can't handle the requirement.

---

## Module 7: Lead Qualification Funnel

A **lead qualification funnel** is the most valuable flow type for service businesses. It does three things: identifies who is worth talking to, collects the information the salesperson needs before the call, and routes qualified leads directly to booking.

### The Four-Question Framework

Most service businesses need to know four things before a sales call is worth scheduling:

1. **Who are you?** (Company type, role, context)
2. **What's the problem?** (What are they trying to solve)
3. **What's the budget?** (Can they afford the solution)
4. **When do they need it?** (Timeline — urgency)

### Building the Qualification Flow

```
[Trigger: DM keyword "QUALIFY" or Intention: "I want to work with you"]
    ↓
[Message: "Hey {first name}! Quick question — what does your business do?"]
    → Wait for reply → Save to field: "business_type"
    ↓
[Message: "Got it. What's the main challenge you're trying to solve right now?"]
    → Wait for reply → Save to field: "main_challenge"
    ↓
[Message: "Makes sense. What's your rough monthly budget for marketing/automation?"]
    → Quick Replies: ["Under $500", "$500-$2K", "$2K-$5K", "$5K+"]
    → Save selected button to field: "budget_range"
    ↓
[Condition: budget_range = "$500-$2K" OR "$2K-$5K" OR "$5K+"]
    YES (qualified) → [Message: "Perfect — let's get you on a call. Book a time here: [Calendly link]"]
                    → [Action: Set tag "qualified-lead"]
                    → [Action: Notify Admin — email with contact details]
    NO (under budget) → [Message: "Thanks for sharing that. We might have some resources that could help — want me to send them over?"]
                      → [Action: Set tag "unqualified-budget"]
                      → [Action: Subscribe to sequence "low-budget-nurture"]
```

### Saving Replies to Custom Fields

When you ask an open-ended question and want to save the answer:

1. In the Message block, click "Save Reply To"
2. Select or create a Custom Field (e.g., "business_type")
3. Set the input type: Text, Number, Email, Phone, Date

The next message can reference it: `Your business type: {business_type}` — useful for personalization.

💡 **PRO TIP:** For budget questions, always use Quick Reply buttons instead of open-ended text. When contacts type their own budget, you get "a lot", "not much", "depends", "idk". Buttons give you clean, actionable data you can branch on. Design your qualification questions to use buttons wherever possible.

---

## Module 8: Multi-Channel Nurture

A **multi-channel nurture sequence** follows up with leads across DM, email, and SMS. The logic is:

1. Initial DM — primary touch
2. If no engagement within 24 hours → email follow-up
3. If no engagement within 48 hours → SMS follow-up (if phone collected)

### Building the Multi-Channel Sequence

**ManyChat Sequences** are time-based message series. Create one:

1. Go to **Automation → Sequences → New Sequence**
2. Name it "Multi-Channel Nurture — New Lead"
3. Add messages with delays:

```
Day 0 (immediate): DM — "Hey {first name}, just checking in. Did you get a chance to look at [lead magnet]?"

Day 1 (24 hours): Email (if email collected) — "Quick follow-up on [topic]"
    → Subject: "Did you get a chance to read this, {first name}?"
    → Body: value content + single CTA

Day 2 (48 hours): DM — "Just want to make sure this got to you! The [resource] is still available if you want it."

Day 4: Email — case study or social proof
    → "Here's how [similar business] got [result]"

Day 7: DM — soft pitch
    → "If you ever want to go deeper on this, I'd be happy to do a quick call. No pressure — just here if it helps."
```

### Sending Emails from ManyChat

ManyChat has basic email functionality. For any client with more than a few hundred contacts, consider a dedicated email provider instead:

| Tool | Best For | Integration |
|------|---------|-------------|
| ManyChat Email | Simple follow-ups, light sequences | Native |
| Mailchimp | Small/mid-size lists, templates | Native integration |
| ActiveCampaign | Advanced automation, lead scoring | Zapier/native |
| Klaviyo | E-commerce clients | Zapier |

For most agency client setups, ManyChat handles the DM touches and email is managed in a dedicated platform, with ManyChat's Action blocks firing webhooks to trigger email sequences.

---

## Module 9: Appointment Booking Flow

The **booking flow** converts qualified leads into scheduled calls.

### Architecture

```
[Trigger: keyword "BOOK" or Intention: "schedule a call"]
    ↓
[Condition: tag "qualified-lead" is set?]
    YES → [Message: "Great! Here are some available times 👇"]
          → [Button: "Book a time" → URL: Calendly link]
          → [Delay: 1 hour]
          → [Condition: tag "call-booked" set? (Calendly webhook sets this)]
                YES → [Message: "You're all set for {appointment_time}! See you then 🎯"]
                NO  → [Message: "Still looking for a time? Here's the link again: [link]"]
    NO (not qualified) → Run them through the 4-question qualification flow first
```

### Calendly Integration

When a contact books via Calendly:
1. Calendly fires a webhook to Zapier/Make.com
2. Zapier/Make.com calls ManyChat API to set tag "call-booked" and field "appointment_time"
3. ManyChat sends a confirmation DM automatically

### Reminders

After booking is confirmed, send two automated reminders:

```
[Delay until 24 hours before appointment_time]
→ [DM: "Just a reminder — we have a call tomorrow at {appointment_time}. Looking forward to it! 🙌"]

[Delay until 1 hour before appointment_time]
→ [DM: "One hour until our call! Here's the link: [meeting link]"]
```

🔥 **CHALLENGE:** Build a complete lead qualification funnel: trigger → 3 qualifying questions with Quick Reply buttons → condition branch (qualified vs. unqualified) → qualified path routes to a Calendly booking link → unqualified path subscribes to a nurture sequence. Test end-to-end.

---

## Exercise: Lead Qualification Funnel with AI Intent

**Deliverable:** A live lead qualification flow that uses Intention Recognition, collects 3 fields, and branches on budget.

**Step 1:** Enable Intention Recognition for your booking/qualification trigger

Write 5 example phrases that express "I want to work with you / I'm interested in your services"

**Step 2:** Build the 3-question qualification flow (business type, main challenge, budget)

Use Quick Reply buttons for the budget question with 4 options

**Step 3:** Add the condition branch:
- Qualified (budget $500+) → Calendly link + "qualified-lead" tag + admin notification
- Unqualified (under $500) → nurture message + "unqualified-budget" tag

**Step 4:** Enable the AI Add-on (or simulate it). Add an AI Step after the initial trigger that handles any unexpected questions before routing into the qualification flow.

**Step 5:** Test the qualified path AND the unqualified path from a secondary account

**Step 6:** Verify in Contacts that both tags are set correctly on your test accounts

---

## Checklist Before Moving On

- [ ] Understand what the ManyChat AI Add-on includes ($29/mo)
- [ ] Know how to configure an AI Step (goal, context, max replies)
- [ ] Understand Intention Recognition vs. Keyword triggers
- [ ] Know how to set up and train a Knowledge Base
- [ ] Understand when to use hybrid architecture (ManyChat + Make.com + OpenAI)
- [ ] Built a 3-question lead qualification flow with condition branching
- [ ] Understand multi-channel nurture (DM → email → SMS)
- [ ] Know how to build an appointment booking flow with reminders

**All boxes checked?** You can build qualification funnels that would take a human sales team weeks to set up. Lesson 4 is where you turn this into a productized agency service.

---

**Next:** [Lesson 4 — Agency Deployment: Integrations, Scaling & Client Delivery](../lesson-04-agency-deployment/LESSON.md)
