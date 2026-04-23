"""
ARCHIVED 2026-04-22 — DO NOT USE. DO NOT IMPORT.
This file is obsolete n8n workflow template code from an earlier lead system.
It previously contained a stale Calendly booking link that caused an agent
hallucination (see memory/CLAUDE_HANDOVER.md). The link has been replaced
with the current Google Calendar link, but the FILE AS A WHOLE is archived.
Authoritative booking link: brain/USER.md → Critical Links section
         or .env.agents → BOOKING_LINK

Build and deploy OASIS Lead System workflows to n8n.
Run: python lead_system/build_workflows.py [reactivation|speed-to-lead|nurture|reputation|all]
"""
import json
import sys
import os

# Add parent dir to path for n8n_tool
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from n8n_tool import N8nClient, load_env


# ============================================================
# Shared credential references (from existing n8n instance)
# ============================================================
CREDS = {
    "gmail": {"id": "peR4lrnX1u4EaMTX", "name": "OASIS GMAIL"},
    "sheets": {"id": "dggWnSXlogDJ34GO", "name": "Oasis Sheets"},
    "openai": {"id": "sRqxdMvX7JkSH8sI", "name": "OpenAi account"},
    "telegram": {"id": "rm2W7woQxCjGMmHr", "name": "LeadAgent Telegram"},
    "calendar": {"id": "zvCQUZlsd8XJbYNY", "name": "OASIS Calendar"},
    "anthropic": {"id": "rXTObLEqFgeMGh4X", "name": "Anthropic account"},
    "gemini": {"id": "RcszApWNCIRIX6Zs", "name": "OASIS Gemini"},
}


def build_lead_reactivation():
    """
    OASIS Lead Reactivation Engine
    3-touch AI-personalized email sequence for dead/old leads.
    Flow: Read leads -> AI personalize -> Send -> Wait -> Check reply -> Follow up -> Alert
    """
    return {
        "name": "OASIS Lead Reactivation Engine",
        "nodes": [
            # === TRIGGERS ===
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "lead-reactivation",
                    "responseMode": "lastNode",
                    "options": {}
                },
                "id": "trigger-webhook",
                "name": "Webhook Trigger",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [220, 300],
                "webhookId": "lead-reactivation-hook"
            },
            {
                "parameters": {},
                "id": "manual-trigger",
                "name": "Manual Test",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [220, 500]
            },

            # === CONFIGURATION ===
            {
                "parameters": {
                    "values": {
                        "string": [
                            {"name": "client_name", "value": "OASIS AI Solutions"},
                            {"name": "sender_name", "value": "Conaugh McKenna"},
                            {"name": "sender_title", "value": "Founder, OASIS AI Solutions"},
                            {"name": "reply_to", "value": "conaugh@oasisaisolutions.com"},
                            {"name": "telegram_chat_id", "value": ""},
                            {"name": "sheet_id", "value": ""},
                            {"name": "sheet_name", "value": "Old Leads"}
                        ],
                        "number": [
                            {"name": "batch_size", "value": 10},
                            {"name": "touch1_wait_days", "value": 3},
                            {"name": "touch2_wait_days", "value": 4}
                        ]
                    },
                    "options": {}
                },
                "id": "config",
                "name": "Campaign Config",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "position": [460, 380]
            },

            # === READ LEADS FROM SHEET ===
            {
                "parameters": {
                    "operation": "read",
                    "sheetId": {"__rl": True, "mode": "list", "value": ""},
                    "sheetName": {"__rl": True, "mode": "list", "value": ""},
                    "options": {}
                },
                "id": "read-leads",
                "name": "Read Old Leads",
                "type": "n8n-nodes-base.googleSheets",
                "typeVersion": 4.5,
                "position": [680, 380],
                "credentials": {"googleSheetsOAuth2Api": CREDS["sheets"]}
            },

            # === FILTER: Must have email ===
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "combinator": "and",
                        "conditions": [
                            {
                                "id": "has-email",
                                "leftValue": "={{ $json.email || $json.Email || $json.EMAIL }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "isNotEmpty"}
                            }
                        ]
                    }
                },
                "id": "filter-email",
                "name": "Has Email?",
                "type": "n8n-nodes-base.filter",
                "typeVersion": 2.2,
                "position": [900, 380]
            },

            # === BATCH PROCESSING ===
            {
                "parameters": {"batchSize": 10, "options": {}},
                "id": "batch",
                "name": "Batch Leads",
                "type": "n8n-nodes-base.splitInBatches",
                "typeVersion": 3,
                "position": [1120, 380]
            },

            # === TOUCH 1: AI-PERSONALIZED REACTIVATION EMAIL ===
            {
                "parameters": {
                    "jsCode": (
                        "// Build the AI prompt for each lead\n"
                        "const items = $input.all();\n"
                        "return items.map(item => {\n"
                        "  const d = item.json;\n"
                        "  const name = d.first_name || d.name || d.Name || d['First Name'] || 'there';\n"
                        "  const email = d.email || d.Email || d.EMAIL;\n"
                        "  const biz = d.business_name || d.company || d.Company || d['Business Name'] || '';\n"
                        "  const interest = d.original_interest || d.service || d.Service || d.notes || d.Notes || 'our services';\n"
                        "  const industry = d.industry || d.Industry || d.category || d.Category || 'local business';\n"
                        "  const lastContact = d.last_contact || d.date || d.Date || 'a while ago';\n"
                        "  return {\n"
                        "    json: {\n"
                        "      ...d,\n"
                        "      _name: name,\n"
                        "      _email: email,\n"
                        "      _biz: biz,\n"
                        "      _interest: interest,\n"
                        "      _industry: industry,\n"
                        "      _lastContact: lastContact,\n"
                        "      _prompt: `Write a short reactivation email for ${name} at ${biz || 'their business'} (${industry}). They originally showed interest in ${interest} around ${lastContact}. `\n"
                        "        + `Rules: 1) Subject: curiosity-driven, no spam words 2) Opening: reference their original interest naturally 3) ONE specific value prop for their industry 4) Social proof: mention a result 5) Soft CTA for 10-min chat 6) Under 150 words, warm tone 7) Sign off as Conaugh McKenna, OASIS AI Solutions. `\n"
                        "        + `Return ONLY JSON: {\"subject\": \"...\", \"body\": \"...\", \"followup_angle\": \"one sentence for day 3 follow-up\"}`\n"
                        "    }\n"
                        "  };\n"
                        "});\n"
                    )
                },
                "id": "prep-prompt",
                "name": "Prepare AI Prompt",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1340, 380]
            },
            {
                "parameters": {
                    "resource": "chat",
                    "model": "gpt-4o-mini",
                    "messages": {
                        "values": [
                            {
                                "content": "={{ $json._prompt }}",
                                "role": "user"
                            }
                        ]
                    },
                    "options": {
                        "temperature": 0.7,
                        "maxTokens": 500
                    }
                },
                "id": "ai-generate",
                "name": "Generate Email (AI)",
                "type": "n8n-nodes-base.openAi",
                "typeVersion": 1.8,
                "position": [1560, 380],
                "credentials": {"openAiApi": CREDS["openai"]}
            },
            {
                "parameters": {
                    "jsCode": (
                        "const items = $input.all();\n"
                        "return items.map(item => {\n"
                        "  const d = item.json;\n"
                        "  const aiText = d.message?.content || d.text || d.output || '';\n"
                        "  let parsed;\n"
                        "  try {\n"
                        "    const match = aiText.match(/\\{[\\\\s\\\\S]*\\}/);\n"
                        "    parsed = JSON.parse(match ? match[0] : aiText);\n"
                        "  } catch(e) {\n"
                        "    parsed = {subject: 'Quick question about your business', body: aiText, followup_angle: 'follow up on challenges'};\n"
                        "  }\n"
                        "  return {json: {...d, email_subject: parsed.subject, email_body: parsed.body, followup_angle: parsed.followup_angle}};\n"
                        "});\n"
                    )
                },
                "id": "parse-ai",
                "name": "Parse AI Response",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1780, 380]
            },

            # === SEND TOUCH 1 ===
            {
                "parameters": {
                    "sendTo": "={{ $json._email }}",
                    "subject": "={{ $json.email_subject }}",
                    "emailType": "text",
                    "message": "={{ $json.email_body }}",
                    "options": {"replyTo": "conaugh@oasisaisolutions.com"}
                },
                "id": "send-touch1",
                "name": "Send Touch 1",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [2000, 300],
                "credentials": {"gmailOAuth2": CREDS["gmail"]}
            },

            # === LOG TOUCH 1 ===
            {
                "parameters": {
                    "operation": "append",
                    "sheetId": {"__rl": True, "mode": "list", "value": ""},
                    "sheetName": {"__rl": True, "mode": "list", "value": "Reactivation Log"},
                    "columns": {
                        "mappingMode": "defineBelow",
                        "value": {
                            "Lead Name": "={{ $json._name }}",
                            "Email": "={{ $json._email }}",
                            "Business": "={{ $json._biz }}",
                            "Subject": "={{ $json.email_subject }}",
                            "Sent At": "={{ new Date().toISOString() }}",
                            "Touch": "1",
                            "Status": "sent",
                            "Follow-up Angle": "={{ $json.followup_angle }}"
                        }
                    },
                    "options": {}
                },
                "id": "log-touch1",
                "name": "Log Touch 1",
                "type": "n8n-nodes-base.googleSheets",
                "typeVersion": 4.5,
                "position": [2000, 500],
                "credentials": {"googleSheetsOAuth2Api": CREDS["sheets"]}
            },

            # === WAIT 3 DAYS ===
            {
                "parameters": {"amount": 3, "unit": "days"},
                "id": "wait-3d",
                "name": "Wait 3 Days",
                "type": "n8n-nodes-base.wait",
                "typeVersion": 1.1,
                "position": [2220, 300]
            },

            # === CHECK FOR REPLY ===
            {
                "parameters": {
                    "operation": "getAll",
                    "returnAll": False,
                    "limit": 3,
                    "filters": {"query": "=from:({{ $json._email }}) newer_than:3d"},
                    "options": {}
                },
                "id": "check-reply-1",
                "name": "Check Reply",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [2440, 300],
                "credentials": {"gmailOAuth2": CREDS["gmail"]}
            },

            # === REPLIED? ===
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "combinator": "and",
                        "conditions": [
                            {
                                "id": "has-reply",
                                "leftValue": "={{ $json.id }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "isNotEmpty"}
                            }
                        ]
                    }
                },
                "id": "if-replied-1",
                "name": "Replied?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [2660, 300]
            },

            # === HOT LEAD ALERT ===
            {
                "parameters": {
                    "chatId": "",
                    "text": "=HOT REACTIVATED LEAD!\n\nName: {{ $json._name }}\nEmail: {{ $json._email }}\nBusiness: {{ $json._biz }}\n\nThey REPLIED to Touch 1!\nCheck Gmail and respond ASAP.",
                    "additionalFields": {}
                },
                "id": "alert-hot-1",
                "name": "Alert: Hot Lead!",
                "type": "n8n-nodes-base.telegram",
                "typeVersion": 1.2,
                "position": [2880, 200],
                "credentials": {"telegramApi": CREDS["telegram"]}
            },

            # === TOUCH 2: FOLLOW-UP ===
            {
                "parameters": {
                    "jsCode": (
                        "const items = $input.all();\n"
                        "return items.map(item => {\n"
                        "  const d = item.json;\n"
                        "  return {json: {...d, _followup_prompt: "
                        "`Write a brief follow-up email (under 80 words) for ${d._name || 'there'}. They didn't reply to our first reactivation email about ${d._interest || 'our services'}. Follow-up angle: ${d.followup_angle || 'check in on their challenges'}. Rules: 1) Subject starts with 'Re: ' 2) Reference first email casually 3) Add ONE new value piece 4) Soft CTA 5) Sign off as Conaugh McKenna. Return ONLY JSON: {\"subject\": \"...\", \"body\": \"...\"}`"
                        "}};\n"
                        "});\n"
                    )
                },
                "id": "prep-touch2",
                "name": "Prepare Touch 2",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [2880, 420]
            },
            {
                "parameters": {
                    "resource": "chat",
                    "model": "gpt-4o-mini",
                    "messages": {
                        "values": [{"content": "={{ $json._followup_prompt }}", "role": "user"}]
                    },
                    "options": {"temperature": 0.7, "maxTokens": 300}
                },
                "id": "ai-touch2",
                "name": "Generate Touch 2 (AI)",
                "type": "n8n-nodes-base.openAi",
                "typeVersion": 1.8,
                "position": [3100, 420],
                "credentials": {"openAiApi": CREDS["openai"]}
            },
            {
                "parameters": {
                    "jsCode": (
                        "const items = $input.all();\n"
                        "return items.map(item => {\n"
                        "  const aiText = item.json.message?.content || item.json.text || '';\n"
                        "  let p;\n"
                        "  try { const m = aiText.match(/\\{[\\\\s\\\\S]*\\}/); p = JSON.parse(m ? m[0] : aiText); }\n"
                        "  catch(e) { p = {subject: 'Re: Quick follow-up', body: aiText}; }\n"
                        "  return {json: {...item.json, t2_subject: p.subject, t2_body: p.body}};\n"
                        "});\n"
                    )
                },
                "id": "parse-touch2",
                "name": "Parse Touch 2",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [3320, 420]
            },
            {
                "parameters": {
                    "sendTo": "={{ $json._email }}",
                    "subject": "={{ $json.t2_subject }}",
                    "emailType": "text",
                    "message": "={{ $json.t2_body }}",
                    "options": {}
                },
                "id": "send-touch2",
                "name": "Send Touch 2",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [3540, 420],
                "credentials": {"gmailOAuth2": CREDS["gmail"]}
            },

            # === WAIT 4 DAYS ===
            {
                "parameters": {"amount": 4, "unit": "days"},
                "id": "wait-4d",
                "name": "Wait 4 Days",
                "type": "n8n-nodes-base.wait",
                "typeVersion": 1.1,
                "position": [3760, 420]
            },

            # === FINAL REPLY CHECK ===
            {
                "parameters": {
                    "operation": "getAll",
                    "returnAll": False,
                    "limit": 3,
                    "filters": {"query": "=from:({{ $json._email }}) newer_than:4d"},
                    "options": {}
                },
                "id": "check-reply-2",
                "name": "Check Reply (Final)",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [3980, 420],
                "credentials": {"gmailOAuth2": CREDS["gmail"]}
            },
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "combinator": "and",
                        "conditions": [
                            {
                                "id": "has-reply-2",
                                "leftValue": "={{ $json.id }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "isNotEmpty"}
                            }
                        ]
                    }
                },
                "id": "if-replied-2",
                "name": "Replied (Final)?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [4200, 420]
            },

            # === HOT LEAD FROM TOUCH 2 ===
            {
                "parameters": {
                    "chatId": "",
                    "text": "=REACTIVATED LEAD (Touch 2)!\n\nName: {{ $json._name }}\nEmail: {{ $json._email }}\n\nReplied after follow-up. Respond NOW.",
                    "additionalFields": {}
                },
                "id": "alert-hot-2",
                "name": "Alert: Touch 2 Reply!",
                "type": "n8n-nodes-base.telegram",
                "typeVersion": 1.2,
                "position": [4420, 320],
                "credentials": {"telegramApi": CREDS["telegram"]}
            },

            # === TOUCH 3: LAST CHANCE ===
            {
                "parameters": {
                    "sendTo": "={{ $json._email }}",
                    "subject": "=Last thing from me, {{ $json._name || 'there' }}",
                    "emailType": "text",
                    "message": "=Hi {{ $json._name || 'there' }},\n\nI know you're busy so I'll make this my last email.\n\nI reached out because I genuinely thought {{ $json._biz || 'your business' }} could benefit from what we're building at OASIS AI - and I still do.\n\nIf the timing's off, I totally get it. But if there's even a small chance this could help you get more customers on autopilot, I'd love 10 minutes of your time.\n\nEither way, wishing you and {{ $json._biz || 'your team' }} all the best.\n\nConaugh McKenna\nOASIS AI Solutions",
                    "options": {}
                },
                "id": "send-touch3",
                "name": "Send Last Chance",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [4420, 520],
                "credentials": {"gmailOAuth2": CREDS["gmail"]}
            },

            # === FINAL LOG ===
            {
                "parameters": {
                    "operation": "append",
                    "sheetId": {"__rl": True, "mode": "list", "value": ""},
                    "sheetName": {"__rl": True, "mode": "list", "value": "Reactivation Log"},
                    "columns": {
                        "mappingMode": "defineBelow",
                        "value": {
                            "Lead Name": "={{ $json._name }}",
                            "Email": "={{ $json._email }}",
                            "Status": "3-touch-complete",
                            "Completed At": "={{ new Date().toISOString() }}",
                            "Touch": "3-final"
                        }
                    },
                    "options": {}
                },
                "id": "log-final",
                "name": "Log Complete",
                "type": "n8n-nodes-base.googleSheets",
                "typeVersion": 4.5,
                "position": [4640, 520],
                "credentials": {"googleSheetsOAuth2Api": CREDS["sheets"]}
            },

            # === CAMPAIGN SUMMARY (Telegram) ===
            {
                "parameters": {
                    "chatId": "",
                    "text": "=Lead Reactivation Campaign Complete\n\n3-touch sequence finished for batch.\nCheck Reactivation Log sheet for full results.",
                    "additionalFields": {}
                },
                "id": "summary",
                "name": "Campaign Summary",
                "type": "n8n-nodes-base.telegram",
                "typeVersion": 1.2,
                "position": [4860, 520],
                "credentials": {"telegramApi": CREDS["telegram"]}
            }
        ],
        "connections": {
            "Webhook Trigger": {"main": [[{"node": "Campaign Config", "type": "main", "index": 0}]]},
            "Manual Test": {"main": [[{"node": "Campaign Config", "type": "main", "index": 0}]]},
            "Campaign Config": {"main": [[{"node": "Read Old Leads", "type": "main", "index": 0}]]},
            "Read Old Leads": {"main": [[{"node": "Has Email?", "type": "main", "index": 0}]]},
            "Has Email?": {"main": [[{"node": "Batch Leads", "type": "main", "index": 0}]]},
            "Batch Leads": {"main": [[{"node": "Prepare AI Prompt", "type": "main", "index": 0}], []]},
            "Prepare AI Prompt": {"main": [[{"node": "Generate Email (AI)", "type": "main", "index": 0}]]},
            "Generate Email (AI)": {"main": [[{"node": "Parse AI Response", "type": "main", "index": 0}]]},
            "Parse AI Response": {"main": [[{"node": "Send Touch 1", "type": "main", "index": 0}, {"node": "Log Touch 1", "type": "main", "index": 0}]]},
            "Send Touch 1": {"main": [[{"node": "Wait 3 Days", "type": "main", "index": 0}]]},
            "Wait 3 Days": {"main": [[{"node": "Check Reply", "type": "main", "index": 0}]]},
            "Check Reply": {"main": [[{"node": "Replied?", "type": "main", "index": 0}]]},
            "Replied?": {"main": [[{"node": "Alert: Hot Lead!", "type": "main", "index": 0}], [{"node": "Prepare Touch 2", "type": "main", "index": 0}]]},
            "Prepare Touch 2": {"main": [[{"node": "Generate Touch 2 (AI)", "type": "main", "index": 0}]]},
            "Generate Touch 2 (AI)": {"main": [[{"node": "Parse Touch 2", "type": "main", "index": 0}]]},
            "Parse Touch 2": {"main": [[{"node": "Send Touch 2", "type": "main", "index": 0}]]},
            "Send Touch 2": {"main": [[{"node": "Wait 4 Days", "type": "main", "index": 0}]]},
            "Wait 4 Days": {"main": [[{"node": "Check Reply (Final)", "type": "main", "index": 0}]]},
            "Check Reply (Final)": {"main": [[{"node": "Replied (Final)?", "type": "main", "index": 0}]]},
            "Replied (Final)?": {"main": [[{"node": "Alert: Touch 2 Reply!", "type": "main", "index": 0}], [{"node": "Send Last Chance", "type": "main", "index": 0}]]},
            "Send Last Chance": {"main": [[{"node": "Log Complete", "type": "main", "index": 0}]]},
            "Log Complete": {"main": [[{"node": "Campaign Summary", "type": "main", "index": 0}]]}
        },
        "settings": {"executionOrder": "v1"},
        "staticData": None,
        "tags": [{"name": "lead-reactivation"}, {"name": "oasis"}, {"name": "client-template"}]
    }


def build_speed_to_lead():
    """
    OASIS Speed-to-Lead AI Responder
    Responds to new leads within 60 seconds via email + logs to sheet.
    Trigger: Webhook from form/ad/CRM -> AI response -> Gmail -> Calendar booking link -> Alert
    """
    return {
        "name": "OASIS Speed-to-Lead Responder",
        "nodes": [
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "speed-to-lead",
                    "responseMode": "responseNode",
                    "options": {}
                },
                "id": "webhook",
                "name": "New Lead Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [220, 300],
                "webhookId": "speed-to-lead-hook"
            },
            {
                "parameters": {},
                "id": "manual",
                "name": "Manual Test",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [220, 500]
            },
            # Normalize incoming data
            {
                "parameters": {
                    "jsCode": (
                        "const items = $input.all();\n"
                        "return items.map(item => {\n"
                        "  const d = item.json.body || item.json;\n"
                        "  return {json: {\n"
                        "    name: d.name || d.first_name || d.Name || d['First Name'] || 'there',\n"
                        "    email: d.email || d.Email || d.EMAIL || '',\n"
                        "    phone: d.phone || d.Phone || d.tel || '',\n"
                        "    business: d.business || d.company || d.Business || d.Company || '',\n"
                        "    service: d.service || d.interest || d.Service || d.Interest || d.message || '',\n"
                        "    source: d.source || d.Source || d.utm_source || 'website',\n"
                        "    received_at: new Date().toISOString()\n"
                        "  }};\n"
                        "});\n"
                    )
                },
                "id": "normalize",
                "name": "Normalize Lead Data",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [460, 380]
            },
            # AI: Generate instant response
            {
                "parameters": {
                    "resource": "chat",
                    "model": "gpt-4o-mini",
                    "messages": {
                        "values": [{
                            "content": "=You are an instant lead responder for OASIS AI Solutions. A new lead just came in. Respond within seconds.\n\nLead: {{ $json.name }}\nBusiness: {{ $json.business || 'Not specified' }}\nInterest: {{ $json.service || 'AI automation' }}\nSource: {{ $json.source }}\n\nWrite a SHORT, warm, immediate response email:\n1. Thank them by name for reaching out\n2. Acknowledge their specific interest\n3. ONE sentence about how OASIS helps businesses like theirs\n4. Include a booking link: https://calendar.app.google/tpfvJYBGircnGu8G8\n5. Under 100 words. Warm, fast, professional.\n6. Sign off: Conaugh McKenna, OASIS AI Solutions\n\nReturn JSON: {\"subject\": \"...\", \"body\": \"...\"}",
                            "role": "user"
                        }]
                    },
                    "options": {"temperature": 0.6, "maxTokens": 300}
                },
                "id": "ai-respond",
                "name": "AI Instant Response",
                "type": "n8n-nodes-base.openAi",
                "typeVersion": 1.8,
                "position": [680, 380],
                "credentials": {"openAiApi": CREDS["openai"]}
            },
            # Parse
            {
                "parameters": {
                    "jsCode": (
                        "const items = $input.all();\n"
                        "return items.map(item => {\n"
                        "  const aiText = item.json.message?.content || item.json.text || '';\n"
                        "  let p;\n"
                        "  try { const m = aiText.match(/\\{[\\\\s\\\\S]*\\}/); p = JSON.parse(m ? m[0] : aiText); }\n"
                        "  catch(e) { p = {subject: 'Thanks for reaching out!', body: aiText}; }\n"
                        "  return {json: {...item.json, resp_subject: p.subject, resp_body: p.body}};\n"
                        "});\n"
                    )
                },
                "id": "parse-resp",
                "name": "Parse Response",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [900, 380]
            },
            # Send email
            {
                "parameters": {
                    "sendTo": "={{ $json.email }}",
                    "subject": "={{ $json.resp_subject }}",
                    "emailType": "text",
                    "message": "={{ $json.resp_body }}",
                    "options": {"replyTo": "conaugh@oasisaisolutions.com"}
                },
                "id": "send-response",
                "name": "Send Instant Email",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [1120, 300],
                "credentials": {"gmailOAuth2": CREDS["gmail"]}
            },
            # Log to sheet
            {
                "parameters": {
                    "operation": "append",
                    "sheetId": {"__rl": True, "mode": "list", "value": ""},
                    "sheetName": {"__rl": True, "mode": "list", "value": "Speed-to-Lead Log"},
                    "columns": {
                        "mappingMode": "defineBelow",
                        "value": {
                            "Name": "={{ $json.name }}",
                            "Email": "={{ $json.email }}",
                            "Phone": "={{ $json.phone }}",
                            "Business": "={{ $json.business }}",
                            "Interest": "={{ $json.service }}",
                            "Source": "={{ $json.source }}",
                            "Responded At": "={{ new Date().toISOString() }}",
                            "Response Time": "< 60 seconds"
                        }
                    },
                    "options": {}
                },
                "id": "log-lead",
                "name": "Log New Lead",
                "type": "n8n-nodes-base.googleSheets",
                "typeVersion": 4.5,
                "position": [1120, 500],
                "credentials": {"googleSheetsOAuth2Api": CREDS["sheets"]}
            },
            # Telegram alert
            {
                "parameters": {
                    "chatId": "",
                    "text": "=NEW LEAD (Speed-to-Lead)\n\nName: {{ $json.name }}\nEmail: {{ $json.email }}\nPhone: {{ $json.phone || 'N/A' }}\nBusiness: {{ $json.business || 'N/A' }}\nInterest: {{ $json.service || 'General' }}\nSource: {{ $json.source }}\n\nAuto-responded in < 60s.\nFollow up personally if high-value.",
                    "additionalFields": {}
                },
                "id": "telegram-alert",
                "name": "Alert: New Lead",
                "type": "n8n-nodes-base.telegram",
                "typeVersion": 1.2,
                "position": [1340, 300],
                "credentials": {"telegramApi": CREDS["telegram"]}
            },
            # Webhook response
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": "={\"status\": \"success\", \"message\": \"Lead received and auto-responded\", \"lead\": \"{{ $json.name }}\"}"
                },
                "id": "respond",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1340, 500]
            }
        ],
        "connections": {
            "New Lead Webhook": {"main": [[{"node": "Normalize Lead Data", "type": "main", "index": 0}]]},
            "Manual Test": {"main": [[{"node": "Normalize Lead Data", "type": "main", "index": 0}]]},
            "Normalize Lead Data": {"main": [[{"node": "AI Instant Response", "type": "main", "index": 0}]]},
            "AI Instant Response": {"main": [[{"node": "Parse Response", "type": "main", "index": 0}]]},
            "Parse Response": {"main": [[{"node": "Send Instant Email", "type": "main", "index": 0}, {"node": "Log New Lead", "type": "main", "index": 0}]]},
            "Send Instant Email": {"main": [[{"node": "Alert: New Lead", "type": "main", "index": 0}]]},
            "Alert: New Lead": {"main": [[{"node": "Respond OK", "type": "main", "index": 0}]]}
        },
        "settings": {"executionOrder": "v1"},
        "tags": [{"name": "speed-to-lead"}, {"name": "oasis"}, {"name": "client-template"}]
    }


def build_reputation_engine():
    """
    OASIS Reputation & Referral Engine
    Auto-request Google reviews + trigger referral offers after service.
    """
    return {
        "name": "OASIS Reputation & Referral Engine",
        "nodes": [
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "review-request",
                    "responseMode": "lastNode",
                    "options": {}
                },
                "id": "webhook",
                "name": "Service Complete Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [220, 300],
                "webhookId": "review-request-hook"
            },
            {
                "parameters": {},
                "id": "manual",
                "name": "Manual Test",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [220, 500]
            },
            # Wait 2 hours after service (don't ask immediately)
            {
                "parameters": {"amount": 2, "unit": "hours"},
                "id": "wait-2h",
                "name": "Wait 2 Hours",
                "type": "n8n-nodes-base.wait",
                "typeVersion": 1.1,
                "position": [460, 380]
            },
            # Send review request email
            {
                "parameters": {
                    "sendTo": "={{ $json.email || $json.Email }}",
                    "subject": "=How was your experience with {{ $json.business_name || 'us' }}?",
                    "emailType": "text",
                    "message": "=Hi {{ $json.customer_name || $json.name || 'there' }},\n\nThank you for choosing {{ $json.business_name || 'us' }}! We hope you had a great experience.\n\nWe'd really appreciate it if you could take 30 seconds to leave us a quick Google review. It helps other people in the community find us:\n\n{{ $json.review_link || '[Google Review Link - configure in settings]' }}\n\nThank you so much for your support!\n\nBest,\n{{ $json.business_name || 'The Team' }}",
                    "options": {}
                },
                "id": "send-review-req",
                "name": "Send Review Request",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [680, 380],
                "credentials": {"gmailOAuth2": CREDS["gmail"]}
            },
            # Wait 3 days then send referral offer
            {
                "parameters": {"amount": 3, "unit": "days"},
                "id": "wait-3d",
                "name": "Wait 3 Days",
                "type": "n8n-nodes-base.wait",
                "typeVersion": 1.1,
                "position": [900, 380]
            },
            # Send referral email
            {
                "parameters": {
                    "sendTo": "={{ $json.email || $json.Email }}",
                    "subject": "=Know someone who could use {{ $json.business_name || 'our services' }}?",
                    "emailType": "text",
                    "message": "=Hi {{ $json.customer_name || $json.name || 'there' }},\n\nWe loved working with you and would love to help others in your network too.\n\nIf you know anyone who could benefit from {{ $json.service_type || 'our services' }}, we'd be happy to offer them a special {{ $json.referral_discount || '10%' }} discount as a thank-you from you.\n\nJust have them mention your name when they reach out, or forward this email to them.\n\nAs a token of our appreciation, you'll also receive {{ $json.referrer_reward || 'a $25 credit' }} for every referral that books with us.\n\nThank you for spreading the word!\n\n{{ $json.business_name || 'The Team' }}",
                    "options": {}
                },
                "id": "send-referral",
                "name": "Send Referral Offer",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [1120, 380],
                "credentials": {"gmailOAuth2": CREDS["gmail"]}
            },
            # Log
            {
                "parameters": {
                    "operation": "append",
                    "sheetId": {"__rl": True, "mode": "list", "value": ""},
                    "sheetName": {"__rl": True, "mode": "list", "value": "Review & Referral Log"},
                    "columns": {
                        "mappingMode": "defineBelow",
                        "value": {
                            "Customer": "={{ $json.customer_name || $json.name }}",
                            "Email": "={{ $json.email || $json.Email }}",
                            "Business": "={{ $json.business_name }}",
                            "Review Requested": "={{ new Date().toISOString() }}",
                            "Referral Sent": "yes",
                            "Status": "complete"
                        }
                    },
                    "options": {}
                },
                "id": "log",
                "name": "Log Activity",
                "type": "n8n-nodes-base.googleSheets",
                "typeVersion": 4.5,
                "position": [1340, 380],
                "credentials": {"googleSheetsOAuth2Api": CREDS["sheets"]}
            }
        ],
        "connections": {
            "Service Complete Webhook": {"main": [[{"node": "Wait 2 Hours", "type": "main", "index": 0}]]},
            "Manual Test": {"main": [[{"node": "Wait 2 Hours", "type": "main", "index": 0}]]},
            "Wait 2 Hours": {"main": [[{"node": "Send Review Request", "type": "main", "index": 0}]]},
            "Send Review Request": {"main": [[{"node": "Wait 3 Days", "type": "main", "index": 0}]]},
            "Wait 3 Days": {"main": [[{"node": "Send Referral Offer", "type": "main", "index": 0}]]},
            "Send Referral Offer": {"main": [[{"node": "Log Activity", "type": "main", "index": 0}]]}
        },
        "settings": {"executionOrder": "v1"},
        "tags": [{"name": "reputation"}, {"name": "referral"}, {"name": "oasis"}, {"name": "client-template"}]
    }


# ============================================================
# DEPLOY
# ============================================================
WORKFLOWS = {
    "reactivation": build_lead_reactivation,
    "speed-to-lead": build_speed_to_lead,
    "reputation": build_reputation_engine,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python lead_system/build_workflows.py [reactivation|speed-to-lead|reputation|all]")
        print("\nAvailable workflows:")
        for name in WORKFLOWS:
            print(f"  {name}")
        return

    env = load_env()
    client = N8nClient(env["N8N_API_URL"], env["N8N_API_KEY"])

    target = sys.argv[1]
    targets = list(WORKFLOWS.keys()) if target == "all" else [target]

    for name in targets:
        if name not in WORKFLOWS:
            print(f"Unknown workflow: {name}")
            continue

        print(f"\nBuilding: {name}...")
        wf_data = WORKFLOWS[name]()
        # n8n API: tags are read-only on create
        wf_data.pop("tags", None)
        result = client.create_workflow(wf_data)
        wf_id = result.get("id", "?")
        wf_name = result.get("name", "?")
        node_count = len(result.get("nodes", []))
        print(f"  Created: {wf_name}")
        print(f"  ID: {wf_id}")
        print(f"  Nodes: {node_count}")
        print(f"  Status: INACTIVE (activate when ready)")
        print(f"  Activate: python scripts/n8n_tool.py activate {wf_id}")


if __name__ == "__main__":
    main()
