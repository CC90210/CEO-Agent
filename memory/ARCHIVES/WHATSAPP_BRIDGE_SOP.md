# SOP: WhatsApp AI Bridge (Community Triage)
**Goal:** Automate 90% of technical community management while maintaining a personal touch.

## 1. ARCHITECTURE
We use **n8n** as the orchestrator to bridge WhatsApp with your **Business-Empire-Agent (BEA)** logic.

*   **Trigger:** Webhook from WhatsApp (via Evolution API, Twilio, or Meta Business API).
*   **Brain:** n8n calls your BEA (via a custom API endpoint or by reading/writing to a shared Supabase table).
*   **Memory:** The agent references `memory/PATTERNS.md` and `memory/SOP_LIBRARY.md` to answer questions.
*   **Action:** n8n sends the response back to WhatsApp using your profile session.

## 2. THE "HUMAN-IN-THE-LOOP" PROTOCOL
To ensure the AI sounds like you and doesn't hallucinate:
1.  **Confidence Score:** If the AI's confidence in an answer is < 85%, it drafts the response but sends it to **YOU** for approval first (via Telegram/Slack).
2.  **Escalation:** If a "High-Ticket" student is identified (via customer ID), the bridge immediately alerts you to take over manually.
3.  **Learning:** Every time you manually answer a question, the n8n workflow appends that answer to your `memory/` logs so the agent learns for next time.

## 3. N8N WORKFLOW NODES
*   **Webhook Node:** Listens for incoming WhatsApp messages.
*   **Filter Node:** Only processes messages in specific community groups.
*   **Supabase Node:** Checks if the student is in the "High-Ticket" or "Standard" tier.
*   **AI Agent Node:** Uses your BEA prompt and local memory files to generate a "human-like" response.
*   **WhatsApp Node:** Sends the final approved message.

## 4. NEXT STEPS
1.  **Evolution API Setup:** Install Evolution API (Open Source) on your server to link your actual WhatsApp account to n8n.
2.  **Workflow Deployment:** Import the "Community Triage" n8n template (I can provide the JSON when you're ready to deploy).
3.  **Tuning:** Run the bridge in "Shadow Mode" for 3 days (logging responses without sending them) to ensure accuracy.

## Obsidian Links
- [[memory/MEMORY_INDEX]] | [[memory/SESSION_LOG]]
