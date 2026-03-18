# Day 8: Business Tools — Stripe, Social Media, and the Money Stack

> **Level:** Architect (Level 3)
> **Duration:** ~2.5 hours
> **Prerequisites:** Day 7 complete
> **Goal:** Connect payment processing and social media automation to your AI stack.

---

## Module 1: Stripe Setup (25 min)

### What Is Stripe?

Stripe handles money on the internet. Accept payments, manage subscriptions, send invoices — all through their API.

**Why Stripe over alternatives:**
- Best developer experience (amazing API docs)
- Handles taxes, compliance, PCI security
- Works in 40+ countries
- Test mode for safe development

### Create Your Account

1. Go to https://stripe.com → Sign up
2. Activate test mode (toggle in top-right: "Test mode")
3. Go to Developers → API Keys
4. Copy your test keys:
   - **Publishable key:** `pk_test_...` (safe for frontend)
   - **Secret key:** `sk_test_...` (backend only, NEVER expose)

Save in `.env`:
```
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
```

### Core Concepts

| Concept | What It Is | Example |
|---------|-----------|---------|
| **Product** | What you're selling | "AI Automation Setup" |
| **Price** | How much and how often | $500/one-time or $99/month |
| **Customer** | Who's paying | jane@company.com |
| **Payment Intent** | A single charge | $500 for setup |
| **Subscription** | Recurring payments | $99/month retainer |
| **Checkout Session** | A payment page | Hosted by Stripe (easiest) |
| **Webhook** | Event notifications | "Payment succeeded" → trigger workflow |

---

## Module 2: Payments & Subscriptions (30 min)

### Create a Product & Price

**In Stripe Dashboard:**
1. Products → Add Product
2. Name: "AI Automation Starter Package"
3. Price: $499 one-time
4. Save

**Via Python SDK:**
```bash
pip install stripe
```

```python
import stripe
import os

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

# Create a product
product = stripe.Product.create(
    name="AI Automation Starter",
    description="Full AI setup: Claude Code + MCPs + automation pipeline"
)

# Create a price
price = stripe.Price.create(
    product=product.id,
    unit_amount=49900,  # $499.00 (amounts in cents)
    currency="usd"
)

print(f"Product: {product.id}")
print(f"Price: {price.id}")
```

### Create a Checkout Session (Easiest Way to Accept Payments)

```python
session = stripe.checkout.Session.create(
    payment_method_types=["card"],
    line_items=[{
        "price": price.id,
        "quantity": 1
    }],
    mode="payment",  # or "subscription" for recurring
    success_url="https://yoursite.com/success",
    cancel_url="https://yoursite.com/cancel"
)

print(f"Checkout URL: {session.url}")
# Send this URL to your customer
```

### Subscriptions

```python
# Create a recurring price
monthly_price = stripe.Price.create(
    product=product.id,
    unit_amount=9900,  # $99/month
    currency="usd",
    recurring={"interval": "month"}
)

# Create checkout for subscription
session = stripe.checkout.Session.create(
    payment_method_types=["card"],
    line_items=[{
        "price": monthly_price.id,
        "quantity": 1
    }],
    mode="subscription",
    success_url="https://yoursite.com/success",
    cancel_url="https://yoursite.com/cancel"
)
```

### Stripe Webhooks

When payments happen, Stripe notifies you:

```python
# In your webhook handler
@app.post("/stripe-webhook")
async def stripe_webhook(request):
    payload = await request.body()
    sig = request.headers["stripe-signature"]

    event = stripe.Webhook.construct_event(
        payload, sig, webhook_secret
    )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # Payment succeeded — activate the customer
        print(f"Payment from: {session['customer_email']}")

    elif event["type"] == "invoice.payment_failed":
        # Subscription payment failed
        print("Payment failed — notify customer")
```

**Or use n8n:** Webhook trigger → process Stripe event → update database → send notification.

---

## Module 3: Social Media APIs — Late (20 min)

### What Is Late?

Late is a social media scheduling and cross-posting API. Write content once, post everywhere.

### Platform Limits

**ALWAYS check these before posting:**

| Platform | Character Limit |
|----------|----------------|
| X (Twitter) | 280 |
| Threads | 500 |
| Instagram | 2,200 |
| LinkedIn | 3,000 |
| TikTok | 4,000 |

### Core Operations

| Action | Description |
|--------|-------------|
| **List accounts** | See connected social accounts |
| **Create post** | Draft/schedule a post |
| **Cross-post** | Same content to multiple platforms |
| **List posts** | See scheduled/published posts |
| **Delete post** | Remove a draft or scheduled post |

### Via MCP (If configured)

```
List my connected social media accounts
```

```
Create a post for LinkedIn:
"AI isn't replacing jobs — it's replacing tasks. The people who learn to direct AI will replace the people who don't. Start learning today."
Schedule it for tomorrow at 9 AM.
```

```
Cross-post this to X, LinkedIn, and Threads:
"Day 8 of the AI Bootcamp. Today we learned about Stripe and social media automation. The future is being built right now."
```

### Via Python

```python
import requests
import os

api_key = os.environ.get("LATE_API_KEY")
headers = {"Authorization": f"Bearer {api_key}"}

# List accounts
response = requests.get(
    "https://api.late.com/accounts",
    headers=headers
)
print(response.json())
```

---

## Module 4: Content Automation Pipeline (25 min)

### The Dream: Write Once, Post Everywhere

```
You write one piece of content
    → AI adapts it for each platform (respecting character limits)
    → Late API schedules posts across all platforms
    → n8n tracks engagement and reports back
```

### Building the Pipeline

**Step 1: Content Generation (Claude Code)**
```
Write a LinkedIn post about [topic].
Then adapt it for X (max 280 chars) and Threads (max 500 chars).
Output all three versions.
```

**Step 2: Schedule with Late**
```
Schedule all three versions:
- LinkedIn: tomorrow 9 AM
- X: tomorrow 9:30 AM
- Threads: tomorrow 10 AM
```

**Step 3: Automate with n8n**
Create a workflow:
```
Cron (every Monday 8 AM)
  → Claude API (generate weekly content)
  → Code node (split into platform-specific versions)
  → Late API (schedule all posts)
  → Email (confirm schedule to you)
```

---

## Module 5: NotebookLM (20 min)

### What Is NotebookLM?

Google's AI research tool. Upload documents → get AI-powered:
- Summaries
- Q&A about your documents
- **Audio podcasts** (two AI hosts discuss your content)
- Study guides and FAQs

### How to Use It

1. Go to https://notebooklm.google.com
2. Create a notebook
3. Upload sources: PDFs, websites, YouTube videos, Google Docs
4. Ask questions about your sources
5. Generate audio overviews (podcast-style discussions)

### Business Use Cases

| Use Case | How |
|----------|-----|
| Client research | Upload client's website, get instant briefing |
| Content creation | Upload your notes, generate blog post outline |
| Training materials | Upload manuals, create study guides |
| Podcasting | Upload any topic, get AI-generated podcast episode |
| Meeting prep | Upload meeting docs, get key points summary |

### Integration with Your Stack

```
NotebookLM generates content/research
    → Download/copy the output
    → Feed into Claude Code for refinement
    → Schedule via Late API
    → Track via n8n
```

---

## Module 6: Agent Command Center Overview (15 min)

### What Bennett Built

The Agent Command Center (dashboard) includes:

| Section | Purpose |
|---------|---------|
| **Overview** | System health, active sessions, uptime |
| **Agents** | Manage AI agent instances |
| **Tasks** | Track what agents are working on |
| **Sessions** | View active/past sessions |
| **Activity** | Real-time activity log |
| **Logs** | System and error logs |
| **Tokens** | Track token usage |
| **Agent Costs** | Monitor spending per agent |
| **Memory** | Agent memory management |
| **Cron** | Scheduled tasks |
| **Webhooks** | External integrations |

### Student Version (Light)

Students get a simplified version:
- Session tracking
- Token/cost monitoring
- Basic logs
- Cron job management

The "cracked" version (CC + Bennett) includes:
- Multi-agent orchestration
- Advanced memory management
- Custom integrations
- Full system health monitoring

### Why This Matters

As a business owner using AI, you need to know:
1. **How much am I spending?** (Token costs)
2. **Is my agent working?** (Session status)
3. **What has it done?** (Activity logs)
4. **Is anything broken?** (Error logs)

The dashboard answers all of these at a glance.

---

## Exercise: The Money Stack

**Step 1:** Set up Stripe test mode
```bash
cd ~/ai-bootcamp/day-08
claude
```

Ask Claude Code:
```
Create a Python script called stripe_setup.py that:
1. Creates a product called "AI Bootcamp Access"
2. Creates two prices: $499 one-time and $99/month subscription
3. Generates checkout URLs for both
4. Prints everything in a clean format
Use my STRIPE_SECRET_KEY from .env
```

**Step 2:** Test the checkout
- Open the checkout URL in your browser
- Use Stripe test card: `4242 4242 4242 4242` (any future date, any CVC)
- Complete the payment
- Check Stripe dashboard — payment should appear

**Step 3:** Social media automation
```
Create a content calendar template as a JSON file (content_calendar.json):
- 5 days of posts
- Each day has: topic, linkedin_text, x_text, threads_text
- Topics: AI tools, automation, business growth, productivity, mindset
- Respect platform character limits
```

**Step 4:** Push to GitHub.

---

## Checklist Before Moving On

- [ ] Stripe account created with test keys
- [ ] Understand products, prices, and checkout sessions
- [ ] Know how Stripe webhooks work
- [ ] Understand Late API for social media scheduling
- [ ] Know platform character limits
- [ ] Explored NotebookLM for research/content
- [ ] Understand the Agent Command Center dashboard
- [ ] Completed the money stack exercise
- [ ] Pushed to GitHub

**All boxes checked?** You can now accept payments and automate content. The money stack is connected.

---

**Next:** [Day 9 — Advanced Agents](../day-09-advanced-agents/LESSON.md)
