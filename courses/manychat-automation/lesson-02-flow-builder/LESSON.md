# Lesson 2: Building Your First Automation — Flow Builder Mastery

> **Level:** Builder (L1)
> **XP Reward:** +250 XP | Running Total: 450 XP
> **Duration:** ~1 hour
> **Prerequisites:** Lesson 1 complete, ManyChat account connected
> **Goal:** Master the Flow Builder well enough to build a complete comment-to-DM lead magnet flow from scratch.

---

## Module 1: The Visual Flow Builder

The **Flow Builder** is ManyChat's drag-and-drop automation editor. Every automation you build lives here. There is no code. Every component is a node you drop on a canvas and connect with arrows.

Open it: **Flows → New Flow → Start from Scratch**

### The Canvas

The canvas is infinite. Flows read left to right — triggers on the left, messages and logic in the middle and right. You connect nodes by dragging from an output port (right side of a node) to an input port (left side of the next node).

### Node Types

Every flow is made of these building blocks:

| Node Type | What It Does | When to Use |
|-----------|-------------|-------------|
| **Trigger** | What starts the flow | Always first — every flow needs one |
| **Message** | Sends content to the contact | Main communication blocks |
| **Condition** | Branches based on logic | Qualifying leads, routing |
| **Action** | Does something in the system | Tags, field updates, notifications |
| **Delay** | Waits before continuing | Follow-up sequences |
| **Smart Delay** | Waits until specific time | Send at optimal time, not immediately |
| **Jump to Flow** | Routes to another flow | Keeping flows modular |
| **Randomizer** | A/B testing split | Testing message variants |

💡 **PRO TIP:** Keep flows focused on one job. A lead magnet flow delivers the lead magnet. A nurture flow does the follow-up. A booking flow handles appointments. When you try to put everything in one flow, it becomes unmaintainable. Use Jump to Flow to chain modular flows.

---

## Module 2: Trigger Types

The trigger determines what event starts the flow. Choose wrong and the flow never fires — or fires when it shouldn't.

### Keyword Trigger (Instagram DM + Messenger)

When a contact sends a specific word in a DM, the flow starts.

Setup:
1. Add trigger → **Keyword**
2. Enter the keyword (e.g., "GUIDE", "FREE", "BOOK")
3. Set match type: **Exact match** (must send exactly that word) or **Contains** (any message with that word)
4. Optionally add multiple keywords (synonyms)

💀 **COMMON MISTAKE:** Using "contains" for common words like "yes" or "help." If someone DMs "yes I have a question about this" — the word "yes" triggers your lead magnet flow. Use "contains" only for distinctive words. Use "exact match" for short single-word triggers.

### Comment Trigger (Instagram)

When someone comments a keyword on a specific post, reel, or any post, ManyChat auto-DMs them.

Setup:
1. Add trigger → **Instagram Comments**
2. Choose: any post, specific post, or specific reel
3. Enter the trigger keyword (the word you're asking people to comment)
4. Add up to 10 keywords (catches variations)

This is the highest-leverage trigger in ManyChat. Every reel becomes a lead generation engine.

### Story Reply Trigger (Instagram)

When someone replies to a specific story, the flow fires.

Setup:
1. Add trigger → **Story Reply**
2. Select the specific story (or "any story")
3. Optionally filter by keyword in the reply

### Follow-to-DM Trigger (Instagram)

When someone follows the account, automatically DM them a welcome message.

Use sparingly. This can feel intrusive if the message is too aggressive. Best use: a soft welcome message with a single CTA, not a hard sell.

### Default Reply

If someone sends a message and no other trigger matches, the Default Reply fires. Every account should have one set.

Use it to:
- Tell people what keywords to use ("Type GUIDE to get our free guide, or BOOK to schedule a call")
- Route to a human ("I'll get back to you shortly — or type URGENT for immediate attention")

### External Trigger (Webhook)

Advanced: an external system sends a webhook to ManyChat and triggers a flow. Used in integrations with CRMs, Zapier, Make.com. Covered in Lesson 4.

---

## Module 3: Message Blocks

Message blocks are the core of every flow. There are several types:

### Text Block

The most common. Plain text message. Supports:
- **Personalization tokens:** `{first name}`, `{last name}`, `{email}` — pulls from contact profile
- **Emojis**
- **Line breaks for readability**

Example:
```
Hey {first name}! 👋

Thanks for commenting — I'm sending you the guide right now.

It covers exactly what you asked about. Read it here 👇
```

### Image Block

Send an image (JPEG, PNG, GIF). Used for:
- Cover images for lead magnets
- Product photos
- Visual hooks before the CTA

### Card (Carousel) Block

A card with a title, subtitle, image, and up to 3 buttons. Multiple cards create a horizontal carousel the user can swipe.

Use for:
- Product listings
- Multiple service options
- Before/after showcases

### Button Block

Add reply buttons to a text message. When the contact taps a button, it triggers the next action. Up to 3 buttons per message on Instagram/Messenger.

Button types:
- **Quick Reply** — contact's reply is captured, flow continues
- **URL** — opens a link
- **Call phone number** — dials a number
- **Go to Flow** — routes to another flow

### Gallery Block

A horizontal scroll of cards. Best for e-commerce, service menus, or course listings.

---

## Module 4: Condition Blocks

**Condition blocks** are where your flows get intelligent. They branch based on what you know about the contact.

### Condition Types

| Condition | Example |
|-----------|---------|
| **Tag is set** | Contact has tag "lead-magnet-downloaded" → don't send again |
| **Custom field value** | Contact's "budget" field = "10k+" → route to premium flow |
| **Subscribed to sequence** | Already in nurture → skip intro |
| **Channel** | Contact is on Instagram vs. Messenger → send channel-appropriate content |
| **Button clicked** | Contact tapped "Yes" → continue; tapped "No" → end |
| **Time of day** | Between 9am-5pm → route to human; outside hours → send bot response |

### Branching Logic

A condition block has two outputs: **YES** and **NO**. Connect both. A flow with a dangling YES or NO branch will drop contacts silently.

```
[Condition: Tag "already-downloaded" is set?]
    YES → [Send: "Looks like you already have this! Want the advanced guide instead?"]
    NO  → [Send the lead magnet → Set tag "already-downloaded"]
```

---

## Module 5: Action Blocks

**Action blocks** perform system operations — they don't send messages, they update records and trigger events.

### Core Actions

| Action | What It Does |
|--------|-------------|
| **Add Tag** | Adds a tag to the contact (e.g., "lead", "qualified", "booked") |
| **Remove Tag** | Removes a tag |
| **Set Custom Field** | Saves a value (e.g., email address, budget, service interest) |
| **Subscribe to Sequence** | Enrolls contact in a time-based sequence |
| **Unsubscribe from Sequence** | Removes from sequence |
| **Notify Admin** | Sends you (or a team member) an email or SMS notification |
| **Send to Zapier/Make** | Fires a webhook to an external system |
| **Convert to Live Chat** | Routes to human agent in Live Chat |

💡 **PRO TIP:** Tags are your segmentation system. Build a tagging convention from day one — for example: `source-instagram`, `stage-lead`, `stage-qualified`, `stage-booked`, `service-seo`, `service-ads`. Consistent tags make analytics and re-targeting possible later.

---

## Module 6: Human Handoff

**When to route to a live agent:** Not every conversation should be automated to completion. The right moment to hand off is when:

1. The lead qualifies and wants to book a call
2. The prospect asks a question the bot can't answer
3. There's a complaint or an unusual situation
4. The contact explicitly asks for a human

Set it up with the **"Convert to Live Chat"** action block. The conversation moves to the Live Chat inbox, and the assigned agent receives a notification.

Always add a fallback message before the handoff:

```
Great — let me connect you with a team member right now. You'll hear back within a few minutes. 🙌
```

💀 **COMMON MISTAKE:** Handing off without a message. The contact gets silence. They assume the bot broke. Always acknowledge the handoff explicitly.

---

## Module 7: Delay Blocks

**Delay blocks** pause the flow before sending the next message.

### Standard Delay

Waits a fixed time: minutes, hours, or days.

Use for follow-up sequences:
- 24 hours after lead magnet delivery → send a value message
- 48 hours after value message → soft pitch

### Smart Delay

Waits until a specific time of day, day of week, or both. Useful for sending messages when the contact is most likely to engage (e.g., 9 AM on a weekday, not 2 AM on Sunday).

---

## Module 8: Build a Comment-to-DM Lead Magnet Flow

This is the core skill. Once you can build this, you can deploy it for any client in under 30 minutes.

### The Flow Architecture

```
[Instagram Comment Trigger: keyword "GUIDE"]
    → [Auto-like the comment] (optional, via Growth Tools)
    → [DM: "Hey {first name}! Here's your guide 👇"] + [Button: "Email it to me" / "I'll read it here"]
        → "Email it to me" branch:
            → [Ask: "What email should I send it to?"]
            → [Wait for reply → Save reply to custom field "email"]
            → [DM: "Perfect! Sent to {email} 📬 You'll get it in a minute."]
            → [Action: Set field "email" = reply, Set tag "email-collected"]
            → [Delay: 24 hours]
            → [DM: Value follow-up message]
            → [Delay: 24 hours]
            → [DM: Soft pitch]
        → "I'll read it here" branch:
            → [DM: Direct link to guide + 1-sentence CTA]
            → [Set tag "lead-magnet-link-sent"]
            → [Delay: 24 hours]
            → [DM: Value follow-up + ask for email]
```

### Build It Step by Step

**Step 1: Create the flow**

Flows → New Flow → Start from Scratch → Name it "Lead Magnet — Comment GUIDE"

**Step 2: Add the trigger**

Click "Add Trigger" → Instagram Comments → Any Post (or select a specific post) → Keyword: "GUIDE"

**Step 3: First DM**

Add a Message block. Set type to Text. Write:

```
Hey {first name}! 👋

You asked for the guide — here it is 👇

[Link to your lead magnet PDF or page]

Want me to email it to you too so you have it saved?
```

Add two Quick Reply buttons: **"Yes, email me!"** and **"No, I'm good"**

**Step 4: Branch on button**

Add a Condition block after the message. Set condition: "Last clicked button = 'Yes, email me!'"

**YES branch → collect email:**

Add a Message block:
```
What email should I send it to?
```

Add a "Wait for Input" option on this block — set it to save the response to a custom field named `email`.

Then add a Message block confirming:
```
Perfect! Sending it to {email} now 📬

Check your inbox in the next few minutes.
```

Then add an Action block: **Set Tag → "email-collected"**

**NO branch → direct link:**

Add a Message block with just the link and a soft CTA:
```
No problem! Here's the direct link 👆

If you ever want it emailed, just reply EMAIL and I'll send it over.
```

Add Action block: **Set Tag → "guide-link-sent"**

**Step 5: Add follow-up delay blocks**

After the email-collected branch:
- Add Delay: 24 hours
- Add Message block (value content — tip related to the lead magnet topic)
- Add Delay: 24 hours
- Add Message block (soft pitch — "If you want help with X, this is how we work with clients...")

**Step 6: Test the flow**

Click "Test Flow" in the top right → choose "Instagram DM" → ManyChat sends you a test message to walk through the flow manually.

Check:
- Does the first message send?
- Do both buttons appear?
- Does the email collection step work?
- Do tags get set correctly? (Check Contacts → find your test contact → verify tags)

**Step 7: Publish**

Toggle the flow status from **Draft** to **Live** in the top right.

Now post something on Instagram with "Comment GUIDE to get our free guide" in the caption. Comment on your own post with "GUIDE" and watch the DM arrive.

⚡ **QUICK WIN:** Before going live for a client, always test the full flow as the end user. Comment the keyword on a test post from a secondary account and walk through every branch. Find broken paths before the client's audience does.

---

## Module 9: Testing and Publishing

### Testing Checklist Before Going Live

- [ ] Walk through every branch manually using "Test Flow"
- [ ] Check that all tags are set correctly after each path
- [ ] Verify the trigger fires (comment the keyword from a secondary account)
- [ ] Confirm email collection saves correctly to the custom field
- [ ] Make sure no branch ends abruptly without a message (dangling paths feel like broken bots)
- [ ] Check that the Default Reply is set (covers cases where the trigger doesn't match)

### Publishing

A flow must be **Live** to fire in production. It can be in Live status and still edited — changes take effect immediately on save.

To pause a flow: toggle back to Draft. Contacts already in-progress won't receive pending messages.

🔥 **CHALLENGE:** Build the full comment-to-DM lead magnet flow above. Publish it. Comment the trigger keyword from a second account. Screenshot the DM you receive and post it in the community.

---

## Exercise: Your First Lead Magnet Flow

**Deliverable:** A live comment-to-DM flow that collects email addresses and delivers a lead magnet.

**Step 1:** Create a flow called "Lead Magnet — Comment [KEYWORD]" (use your own keyword)

**Step 2:** Set the trigger: Instagram Comments → keyword of your choice

**Step 3:** Build the two-branch flow: email collection path + direct link path

**Step 4:** Add a 24-hour follow-up value message to the email-collected branch

**Step 5:** Test the flow using "Test Flow" — walk through both branches

**Step 6:** Publish the flow and comment the trigger keyword on an Instagram post

**Step 7:** Verify in Contacts that your test account received the correct tags

---

## Checklist Before Moving On

- [ ] Understand all node types: trigger, message, condition, action, delay
- [ ] Know the 5+ trigger types and when to use each
- [ ] Can build message blocks with personalization tokens
- [ ] Understand condition branching (YES/NO paths)
- [ ] Know what action blocks do (tags, fields, notifications)
- [ ] Know when to use human handoff
- [ ] Built and published a comment-to-DM lead magnet flow
- [ ] Tested the flow end-to-end from a secondary account

**All boxes checked?** You can build the most valuable flow in the ManyChat arsenal. Lesson 3 takes this further with AI integration and advanced qualification.

---

**Next:** [Lesson 3 — Advanced Flows: AI Integration, Lead Qualification & Multi-Channel](../lesson-03-ai-advanced/LESSON.md)
