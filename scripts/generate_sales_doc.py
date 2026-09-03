"""Generate sales doc — provides build html content."""

import os
import sys
import subprocess
import json

def build_html_content():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OASIS AI Solutions - Sales Enablement & Product Master Guide</title>
<style>
    body {
        font-family: Arial, Helvetica, sans-serif;
        line-height: 1.6;
        color: #1e293b;
        margin: 40px;
    }
    h1 {
        color: #0f172a;
        font-size: 26pt;
        border-bottom: 2px solid #0284c7;
        padding-bottom: 8px;
        margin-top: 24px;
        margin-bottom: 16px;
    }
    h2 {
        color: #0369a1;
        font-size: 18pt;
        border-bottom: 1px solid #cbd5e1;
        padding-bottom: 6px;
        margin-top: 28px;
        margin-bottom: 14px;
    }
    h3 {
        color: #0f172a;
        font-size: 14pt;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    h4 {
        color: #334155;
        font-size: 12pt;
        margin-top: 14px;
        margin-bottom: 6px;
    }
    p {
        margin-bottom: 12px;
        font-size: 11pt;
    }
    ul, ol {
        margin-top: 4px;
        margin-bottom: 14px;
        padding-left: 24px;
    }
    li {
        margin-bottom: 6px;
        font-size: 11pt;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 18px 0;
        font-size: 10.5pt;
    }
    th, td {
        border: 1px solid #cbd5e1;
        padding: 10px 12px;
        text-align: left;
    }
    th {
        background-color: #f1f5f9;
        color: #0f172a;
        font-weight: bold;
    }
    tr:nth-child(even) {
        background-color: #f8fafc;
    }
    blockquote {
        background-color: #f0f9ff;
        border-left: 4px solid #0284c7;
        margin: 16px 0;
        padding: 12px 18px;
        font-style: italic;
        color: #0369a1;
    }
    .callout {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 5px solid #0284c7;
        padding: 14px 18px;
        margin: 16px 0;
        border-radius: 4px;
    }
    .callout-title {
        font-weight: bold;
        color: #0f172a;
        margin-bottom: 6px;
        font-size: 11.5pt;
    }
    .badge {
        display: inline-block;
        background-color: #e0f2fe;
        color: #0369a1;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 9.5pt;
        font-weight: bold;
    }
    .highlight {
        background-color: #fef08a;
        padding: 2px 4px;
    }
    hr {
        border: 0;
        height: 1px;
        background: #cbd5e1;
        margin: 30px 0;
    }
</style>
</head>
<body>

<h1>OASIS AI Solutions — Sales Enablement &amp; Product Master Guide</h1>
<p><strong>Version:</strong> 2.0 (Updated 2026) | <strong>Classification:</strong> Internal Sales Enablement Document | <strong>Audience:</strong> OASIS AI Sales Representatives, Appointment Setters, &amp; Closers</p>

<div class="callout">
    <div class="callout-title">DOCUMENT PURPOSE &amp; EXECUTIVE MANDATE</div>
    <p>This master guide is the single source of truth for all sales representatives at <strong>OASIS AI Solutions</strong>. It details our identity, ideal client profile, core product offerings, pricing architecture, commission structures, sales methodology (NEPQ), call scripts, and objection handling frameworks. Master this document to communicate value with total confidence, diagnose client bottlenecks, and achieve high conversion rates.</p>
</div>

<hr>

<h2>1. Executive Summary &amp; Company Overview</h2>

<h3>1.1 Who We Are</h3>
<p><strong>OASIS AI Solutions</strong> is a website-first growth systems agency for local-service Small and Medium-sized Businesses (SMBs) across Canada and the United States. Headquartered in Montreal, Quebec (with roots in Collingwood, Ontario), OASIS AI was founded by <strong>Conaugh McKenna</strong> and co-founded by <strong>Adon</strong>.</p>

<h3>1.2 Our Core Philosophy</h3>
<p>We believe that a local business's website is the single most critical asset in its sales funnel. However, most local business websites are outdated, mobile-broken, slow, and leak qualified leads daily. Furthermore, when leads do reach out, manual follow-up delays (slow speed-to-lead) cause up to 50% of potential buyers to go to competitors.</p>
<p>OASIS AI fixes this by delivering <strong>conversion-focused website rebuilds</strong> as the primary entry product, and prescribing <strong>focused AI automations</strong> whenever discovery exposes operational leaks in lead capture, missed calls, booking, or review collection.</p>

<h3>1.3 Our Market Differentiation</h3>
<ul>
    <li><strong>Builders, Not Resellers:</strong> We are deep technical engineers and operators who custom-build and maintain our client systems. We are not generic white-label tool resellers.</li>
    <li><strong>Outcome &amp; Revenue Focused:</strong> We don't sell vanity metrics or flashy AI hype. We sell measurable phone calls, quote requests, booked appointments, and saved labor hours.</li>
    <li><strong>No Long-Term Traps:</strong> We build trust through results. Setup fees cover the custom build, and month-to-month maintenance keeps client systems optimized without locking them into predatory annual contracts.</li>
</ul>

<hr>

<h2>2. Ideal Client Profile (ICP) &amp; Target Markets</h2>

<p>Sales reps must focus 100% of their outreach and discovery on businesses that fit our ICP. Do not waste time on Anti-ICP prospects.</p>

<h3>2.1 Primary Target Verticals</h3>
<table>
    <thead>
        <tr>
            <th>Vertical</th>
            <th>Examples</th>
            <th>Primary Pain Points</th>
            <th>Key Pitch Angle</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><strong>Trades &amp; Home Services</strong></td>
            <td>HVAC, Plumbing, Electrical, Roofing, Landscaping, Remodeling</td>
            <td>Missed calls while on jobs, slow quote follow-up, poor mobile website layout.</td>
            <td>Emergency click-to-call, instant missed-call SMS recovery, quote nurture automation.</td>
        </tr>
        <tr>
            <td><strong>Wellness &amp; Healthcare</strong></td>
            <td>Physiotherapy, Chiropractic, Massage, Med Spas, Dental Clinics</td>
            <td>High appointment no-show rates, manual phone booking, review collection gaps.</td>
            <td>24/7 mobile self-booking, deposit collection, automated SMS reminders &amp; review engine.</td>
        </tr>
        <tr>
            <td><strong>Professional Services</strong></td>
            <td>Accountants, Legal Practices, Bookkeepers, Local Consultants</td>
            <td>Friction-heavy intake forms, manual document requests, weak online authority.</td>
            <td>High-authority conversion design, automated document/intake routing, instant email response.</td>
        </tr>
        <tr>
            <td><strong>Repeat Customer SMBs</strong></td>
            <td>Auto Detailing, Property Maintenance, Cleaning Services</td>
            <td>Dormant past customers, manual billing/invoicing, zero follow-up.</td>
            <td>Reactivation campaigns, automated recurring bookings &amp; Stripe invoice links.</td>
        </tr>
    </tbody>
</table>

<h3>2.2 Qualification Criteria (The Ideal Client)</h3>
<ul>
    <li><strong>Active Client Base:</strong> 50+ existing/past customers.</li>
    <li><strong>Revenue Floor:</strong> $20,000 to $200,000+ per month in revenue (must easily afford a $2,000–$5,000 setup + monthly retainer).</li>
    <li><strong>High Lead Friction:</strong> Currently losing leads due to slow response times, manual pen-and-paper intake, or an outdated website.</li>
    <li><strong>Owner Involvement:</strong> Owner-operated or small office team where manual tasks eat up valuable management hours.</li>
    <li><strong>Local Search Visibility Needs:</strong> Operates in a competitive local market where speed-to-lead and trust decide who gets the job.</li>
</ul>

<h3>2.3 Anti-ICP (Do Not Pursue)</h3>
<div class="callout" style="border-left-color: #ef4444; background-color: #fef2f2;">
    <div class="callout-title" style="color: #991b1b;">STRICT DO NOT PURSUE LIST:</div>
    <ul>
        <li><strong>Pure E-Commerce / Dropshipping:</strong> Requires Shopify/DTC stacks; outside our SMB local-service model.</li>
        <li><strong>SaaS / Tech Startups:</strong> Require custom software dev rather than growth/conversion systems.</li>
        <li><strong>Micro-Businesses (&lt; $10k/mo revenue):</strong> Cannot afford setup deposits or retainers and take up excessive support time.</li>
        <li><strong>DIY Tech Seekers:</strong> Business owners who want us to teach them how to build it or just buy raw prompt templates.</li>
    </ul>
</div>

<hr>

<h2>3. The OASIS Product &amp; Service Suite (What We Sell)</h2>

<p>OASIS AI Solutions delivers a modular two-part product stack: <strong>The Conversion Core (Website)</strong> and <strong>The AI Automation Suite</strong>.</p>

<h3>3.1 Primary Entry Product: Conversion-Centric Website Systems</h3>
<p>We do not build generic brochure websites. We build conversion engines structured to turn website visitors into phone calls and form submissions within 30 seconds of landing.</p>

<ul>
    <li><strong>Mobile-First UX:</strong> Over 70% of local service traffic is mobile. Sticky click-to-call buttons, thumb-friendly navigation, and sub-2-second load speeds.</li>
    <li><strong>Conversion Architecture:</strong> Clear value proposition above the fold, prominent quote/booking triggers, and friction-free intake forms.</li>
    <li><strong>Trust &amp; Authority Layer:</strong> Google review integration, local service area maps, licenses, certifications, and before-and-after proof galleries.</li>
    <li><strong>Local SEO Foundations:</strong> Schema markup, Google Business Profile alignment, meta tags, and location-page structures.</li>
    <li><strong>Managed Hosting &amp; Infrastructure:</strong> Ultra-fast CDN hosting, SSL security, daily cloud backups, analytics tracking, and managed DNS setup.</li>
</ul>

<h3>3.2 Prescribed AI Automations Suite</h3>
<p>Automations are <em>never</em> sold as raw tech or standalone software. They are prescribed when discovery reveals an operational leak in the client's sales process.</p>

<table>
    <thead>
        <tr>
            <th>Automation Module</th>
            <th>What It Does</th>
            <th>Business Outcome / Impact</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><strong>1. Speed-to-Lead &amp; CRM Routing</strong></td>
            <td>Fires an automated AI SMS &amp; email response within 60 seconds of a web form submission. Routes lead to CRM/Command Center.</td>
            <td>Eliminates lead decay. Increases lead conversion rates by up to 391% by being first to respond.</td>
        </tr>
        <tr>
            <td><strong>2. Missed-Call &amp; Quote Recovery</strong></td>
            <td>Triggers instant text-back when an incoming call goes unanswered. Runs a multi-touch follow-up sequence for open quotes.</td>
            <td>Recovers 30%–50% of lost missed-call inquiries into booked jobs without adding office staff.</td>
        </tr>
        <tr>
            <td><strong>3. AI Booking &amp; Reminder System</strong></td>
            <td>Self-serve appointment scheduling (Cal.com integration), collects deposits via Stripe, sends SMS/email reminders.</td>
            <td>Reduces no-shows by 70%+, automates deposit collection, and fills calendar 24/7.</td>
        </tr>
        <tr>
            <td><strong>4. Google Review &amp; Reputation Engine</strong></td>
            <td>Automated post-service SMS/Email review request sequence sent upon job completion, plus referral loops.</td>
            <td>Drives 5-star Google reviews consistently, boosting local search ranking and trust.</td>
        </tr>
        <tr>
            <td><strong>5. Gmail &amp; Communication Classifier</strong></td>
            <td>AI monitors client inbox, categorizes inquiries, alerts priority calls, and drafts responses for approval.</td>
            <td>Saves owner 5–10 hours per week on email triage and administrative drafting.</td>
        </tr>
        <tr>
            <td><strong>6. Invoice &amp; Document Generator</strong></td>
            <td>Automated proposal, estimate, and invoice generation integrated directly with Stripe payment gateways.</td>
            <td>Accelerates cash flow and eliminates manual invoice creation delays.</td>
        </tr>
    </tbody>
</table>

<hr>

<h2>4. Pricing Architecture &amp; Package Tiers</h2>

<p>OASIS AI presents three standardized tiers. Always present pricing using the <strong>Goldilocks Anchoring Strategy</strong> (present Authority first, Growth second, Essential third).</p>

<table>
    <thead>
        <tr>
            <th>Package Tier</th>
            <th>Setup Deposit</th>
            <th>Monthly Maintenance</th>
            <th>Included Core Scope</th>
            <th>Target Client</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><strong>Essential</strong></td>
            <td><strong>$2,000</strong> setup</td>
            <td><strong>$250</strong> / month</td>
            <td>Conversion Website Rebuild + Managed Hosting, Security, Local SEO Foundations, Analytics, Review Follow-Up Foundation.</td>
            <td>Smaller SMBs looking to fix a broken website and build local trust.</td>
        </tr>
        <tr>
            <td><strong>Growth<br><span class="badge">RECOMMENDED</span></strong></td>
            <td><strong>$3,500</strong> setup</td>
            <td><strong>$350</strong> / month</td>
            <td>Everything in Essential <strong>PLUS 1 Approved Custom AI Automation</strong> (e.g. Speed-to-Lead or Missed-Call Recovery).</td>
            <td>Established SMBs losing leads to slow follow-up or manual scheduling. (Our primary volume seller).</td>
        </tr>
        <tr>
            <td><strong>Authority</strong></td>
            <td><strong>$5,000+</strong> setup</td>
            <td><strong>$500+</strong> / month</td>
            <td>Everything in Growth <strong>PLUS 2 Approved Custom AI Automations</strong>, priority SLA support, custom dashboards &amp; analytics.</td>
            <td>Market leaders seeking full-stack operational automation and rapid expansion.</td>
        </tr>
    </tbody>
</table>

<div class="callout">
    <div class="callout-title">CURRENCY &amp; PAYMENT TERMS CONTRACT:</div>
    <ul>
        <li><strong>Currency Standard:</strong> Use <strong>CAD</strong> for Canadian clients and <strong>USD</strong> for U.S. clients (do not convert numbers; keep nominal values identical).</li>
        <li><strong>Deposit Structure:</strong> <strong>50% setup deposit upfront</strong> upon contract signing; remaining <strong>50% setup balance prior to official site launch</strong>.</li>
        <li><strong>Monthly Maintenance Start:</strong> Monthly recurring billing begins on launch day. Covers hosting, SSL, backups, analytics, software maintenance, and ongoing support.</li>
    </ul>
</div>

<hr>

<h2>5. Sales Rep Roles, Compensation &amp; Pipeline Stages</h2>

<h3>5.1 Sales Rep Role Definition</h3>
<p>As an OASIS AI Sales Representative, your core responsibility is to be an <strong>Appointment Setter &amp; Qualifier</strong>. You identify visible website friction on target SMB sites, connect those issues to lost calls/revenue, qualify the decision-maker, and book a Google Meet with founders <strong>Conaugh McKenna (CC)</strong> or <strong>Adon</strong>.</p>
<p><em>Reps who demonstrate high qualification consistency earn promotion to the <strong>Closer Track</strong>, where they run the founder demo, present proposals, and close deals independently.</em></p>

<h3>5.2 Commission Structure (Flat Setup Commission)</h3>
<p>Commission is paid directly on collected setup deposit revenue:</p>

<table>
    <thead>
        <tr>
            <th>Track</th>
            <th>Commission Rate</th>
            <th>Essential ($2K Setup)</th>
            <th>Growth ($3.5K Setup)</th>
            <th>Authority ($5K Setup)</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><strong>Opener Track</strong><br>(Book Call -&gt; Founder Closes)</td>
            <td><strong>20%</strong> of collected setup</td>
            <td>$400 payout</td>
            <td>$700 payout</td>
            <td>$1,000 payout</td>
        </tr>
        <tr>
            <td><strong>Closer Track</strong><br>(Rep Runs Demo &amp; Closes)</td>
            <td><strong>30%</strong> of collected setup</td>
            <td>$600 payout</td>
            <td>$1,050 payout</td>
            <td>$1,500 payout</td>
        </tr>
    </tbody>
</table>

<h3>5.3 Rep Pipeline Stages (Button-by-Button Workflow)</h3>
<ol>
    <li><strong>Assigned:</strong> Review pre-researched lead, audit findings, observed website friction, and contact info. Make the first call.</li>
    <li><strong>Attempting Contact:</strong> Select "No Answer" or "Voicemail Left" and set a mandatory next follow-up action date/time. Never leave a lead without a scheduled next step.</li>
    <li><strong>Connected:</strong> Conduct NEPQ discovery. Identify pain, verify decision-maker status, and confirm budget availability ($2,000+ setup).</li>
    <li><strong>Qualified:</strong> Open the OASIS Google Meet calendar link, select founder (CC or Adon), confirm meeting time with prospect, and record detailed audit notes.</li>
    <li><strong>Founder Meeting:</strong> Handoff complete. The founder now owns the demo, proposal, and close. Attribution remains locked to the qualifying rep.</li>
</ol>

<hr>

<h2>6. NEPQ Sales Methodology &amp; Scripting Framework</h2>

<p>OASIS AI sales calls follow Jeremy Miner's <strong>NEPQ (Neuro-Emotional Persuasion Questions)</strong> framework. The golden rule of NEPQ: <em>Questions sell better than pitching. Lead with their problem, not your product.</em></p>

<h3>6.1 The 7-Phase NEPQ Call Framework</h3>

<h4>Phase 1: Connection &amp; Pattern Interrupt (First 30 Seconds)</h4>
<p>Goal: Eliminate pressure and sound completely different from typical pushy salespeople.</p>
<blockquote>
    "Hey [Name], it's [Rep Name] with OASIS. I'll be completely upfront—this is a cold call. I was looking at [Company Name]'s website and noticed a couple of things that might be costing you calls. Mind if I take 30 seconds to explain why I called, and if it's not relevant, you can just hang up on me? Fair enough?"
</blockquote>

<h4>Phase 2: Situation Questions (2–3 Minutes)</h4>
<p>Goal: Understand their current lead flow and website setup without assuming.</p>
<ul>
    <li>"Walk me through what happens right now when someone lands on your website looking for an estimate?"</li>
    <li>"When a call comes in while your team is out on a job site, who answers it?"</li>
    <li>"How many inquiries would you say come through the website in a typical week?"</li>
</ul>

<h4>Phase 3: Problem Awareness Questions (3–5 Minutes)</h4>
<p>Goal: Help the prospect feel the real cost and frustration of their current bottleneck.</p>
<ul>
    <li>"What happens when a prospect fills out a form or calls after hours and doesn't get an answer for a few hours?"</li>
    <li>"How much revenue would you estimate you're losing each month from those missed calls or slow follow-ups?"</li>
    <li>"On a scale of 1 to 10, how satisfied are you with how well your website turns visitors into paying customers?"</li>
</ul>

<h4>Phase 4: Solution Awareness Questions (2–3 Minutes)</h4>
<p>Goal: Get the prospect to describe their ideal outcome in their own words.</p>
<ul>
    <li>"If you could wave a magic wand, what would your ideal customer booking flow look like?"</li>
    <li>"If your website automatically captured and responded to every inquiry in 30 seconds, what would that do for your monthly revenue?"</li>
</ul>

<h4>Phase 5: Consequence Questions (1–2 Minutes)</h4>
<p>Goal: Surface the real cost of doing nothing.</p>
<ul>
    <li>"What happens if you leave the website and follow-up as-is for the next 6 months while competitors in [City] upgrade theirs?"</li>
    <li>"What's the cost of doing nothing here?"</li>
</ul>

<h4>Phase 6: Tailored Positioning (3–5 Minutes)</h4>
<p>Goal: Present our solution using <em>their exact words</em> and pain points.</p>
<blockquote>
    "Based on what you just shared, [Name]—specifically that you're losing about 5 quotes a month because calls go to voicemail while you're on job sites—here's what we do. OASIS rebuilds your website around mobile conversion first so clients can instantly click-to-call or request a quote. Then we attach an automated missed-call recovery system that texts missed callers in 30 seconds. That way, you capture the job before they call someone else."
</blockquote>

<h4>Phase 7: The Low-Pressure Booking Close</h4>
<p>Goal: Secure the founder Google Meet appointment.</p>
<blockquote>
    "I don't scope or price custom builds on a cold call. I'd like to put you on a 20-minute Google Meet with our founder, Conaugh, where he'll walk you through a free site audit and show you exact examples. Do you have your calendar handy for Thursday at 10 AM or 2 PM?"
</blockquote>

<hr>

<h2>7. Objection Handling Master Matrix</h2>

<p>Never argue with a prospect. Use the <strong>Acknowledge, Clarify, Reframe, &amp; Guide</strong> method.</p>

<table>
    <thead>
        <tr>
            <th>Objection</th>
            <th>Root Cause</th>
            <th>Exact Response Script</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><strong>"Send me an email / send info"</strong></td>
            <td>Brush-off; low perceived value.</td>
            <td>"I'd be happy to. So I send over the right details—should I focus the breakdown on the mobile layout issue or the missed-call follow-up side? ... Great, I'll email that over, but let's grab 15 minutes on Thursday so I can walk you through the live audit. Does morning or afternoon work better?"</td>
        </tr>
        <tr>
            <td><strong>"We already have a web designer / agency"</strong></td>
            <td>Loyalty or feeling covered.</td>
            <td>"That's great! Are they focused primarily on design maintenance, or are they actively optimizing your speed-to-lead and conversion rates? ... We often complement existing web teams by adding the automated follow-up engine they don't build."</td>
        </tr>
        <tr>
            <td><strong>"It's too expensive / We don't have budget"</strong></td>
            <td>Price shock or unperceived ROI.</td>
            <td>"I completely understand. Just to clarify, our entry package starts at $2,000 setup. If recovering just ONE missed HVAC job pays back that entire investment, would it be worth evaluating the math with our founder?"</td>
        </tr>
        <tr>
            <td><strong>"We get all our business from word of mouth / referrals"</strong></td>
            <td>False sense of security.</td>
            <td>"Referrals are the best business! But let me ask you—when a referral gets your name, what's the first thing they do? They Google your site on their phone. If your site looks outdated or hard to navigate, how many of those referrals are quietly dropping off before calling?"</td>
        </tr>
        <tr>
            <td><strong>"I don't have time right now"</strong></td>
            <td>Timing / busyness.</td>
            <td>"I get it—you're running a business. That's actually why we called; your manual follow-up is eating your time. If 20 minutes with our founder saves your team 10 hours a week, when would be a realistic day to look at that?"</td>
        </tr>
    </tbody>
</table>

<hr>

<h2>8. Operations, Onboarding &amp; Fulfillment SOP</h2>

<p>Understanding what happens after a close gives reps authority when talking to prospects.</p>

<ol>
    <li><strong>Deposit &amp; Contract:</strong> Proposal signed and 50% setup deposit collected via Stripe invoice link.</li>
    <li><strong>Client Onboarding (Day 1–3):</strong> Client completes digital onboarding intake (brand assets, logo, domain/DNS access, services list, location details).</li>
    <li><strong>Scaffold &amp; Design Build (Week 1–2):</strong> OASIS engineering team builds high-converting mobile layout and staging site.</li>
    <li><strong>Automation Integration (Week 2–3):</strong> Custom AI automations (CRM routing, missed-call SMS, booking calendar) connected and tested in staging.</li>
    <li><strong>QA &amp; Final Review (Week 3–4):</strong> 11-point QA check (Mobile layout, Speed, Local SEO, Forms, Payment Links, Backup, Security). Client signs off on final build.</li>
    <li><strong>Final Balance &amp; Launch (Launch Day):</strong> Remaining 50% setup balance collected. DNS cutover goes live. Monthly maintenance billing begins.</li>
</ol>

<hr>

<div class="callout" style="border-left-color: #10b981; background-color: #ecfdf5;">
    <div class="callout-title" style="color: #065f46;">FINAL SALES MANDATE FOR ALL REPS</div>
    <p style="color: #064e3b;">Remember: You are selling freedom, professionalism, and revenue to local business owners who are overwhelmed by manual work and lost opportunities. Approach every call with curiosity, diagnose their friction with precision, and lead them to the obvious next step: a discovery call with OASIS AI Solutions.</p>
</div>

</body>
</html>
"""
    return html

def main():
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    html_path = os.path.join(tmp_dir, "oasis_sales_enablement_master_guide.html")
    
    html_content = build_html_content()
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"Wrote HTML file to: {html_path}")
    
    # Now run google_tool.py docs create
    cmd = [
        sys.executable,
        "scripts/integrations/google_tool.py",
        "docs",
        "create",
        "--title", "OASIS AI Solutions - Sales Enablement and Product Master Guide",
        "--html", os.path.relpath(html_path, os.getcwd())
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
    
if __name__ == "__main__":
    main()
