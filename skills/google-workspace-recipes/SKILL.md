---
name: google-workspace-recipes
version: 1.0.0
description: "Cookbook of multi-step Google Workspace workflows (Gmail + Drive + Calendar + Docs + Sheets + Tasks)."
tags: [skills, google-workspace, recipes, cookbook]
metadata:
  openclaw:
    category: "recipe"
    domain: "productivity"
    requires:
      bins: ["gws"]
---

# Google Workspace Recipes — Cookbook

> Multi-step recipes combining `gws` CLI commands. Each recipe solves a concrete productivity workflow.
> Single source of truth — replaces 41 individual `recipe-*` skill files.
> [[skills/INDEX]] | [[brain/CAPABILITIES]]

## Prerequisites

- The `gws` binary must be on `$PATH`. See `skills/gws-shared/SKILL.md` for auth and global flags.
- Each recipe lists which parent skills to consult for command-level details (`gws-gmail`, `gws-drive`, etc.).

## Recipe Index

### Email & Gmail
- [Create a Gmail Filter](#create-gmail-filter) — Create a Gmail filter to automatically label, star, or categorize incoming messages.
- [Set Up a Gmail Vacation Responder](#create-vacation-responder) — Enable a Gmail out-of-office auto-reply with a custom message and date range.
- [Draft a Gmail Message from a Google Doc](#draft-email-from-doc) — Read content from a Google Doc and use it as the body of a Gmail message.
- [Email a Google Drive File Link](#email-drive-link) — Share a Google Drive file and email the link with a message to recipients.
- [Forward Labeled Gmail Messages](#forward-labeled-emails) — Find Gmail messages with a specific label and forward them to another address.
- [Label and Archive Gmail Threads](#label-and-archive-emails) — Apply Gmail labels to matching messages and archive them to keep your inbox clean.
- [Save Gmail Attachments to Google Drive](#save-email-attachments) — Find Gmail messages with attachments and save them to a Google Drive folder.
- [Save a Gmail Message to Google Docs](#save-email-to-doc) — Save a Gmail message body into a Google Doc for archival or reference.

### Drive & Files
- [Export a Google Sheet as CSV](#backup-sheet-as-csv) — Export a Google Sheets spreadsheet as a CSV file for local backup or processing.
- [Bulk Download Drive Folder](#bulk-download-folder) — List and download all files from a Google Drive folder.
- [Create and Configure a Shared Drive](#create-shared-drive) — Create a Google Shared Drive and add members with appropriate roles.
- [Find Largest Files in Drive](#find-large-files) — Identify large Google Drive files consuming storage quota.
- [Organize Files into Google Drive Folders](#organize-drive-folder) — Create a Google Drive folder structure and move files into the right locations.
- [Share a Google Drive Folder with a Team](#share-folder-with-team) — Share a Google Drive folder and all its contents with a list of collaborators.
- [Watch for Drive Changes](#watch-drive-changes) — Subscribe to change notifications on a Google Drive file or folder.

### Calendar & Events
- [Add Multiple Attendees to a Calendar Event](#batch-invite-to-event) — Add a list of attendees to an existing Google Calendar event and send notifications.
- [Block Focus Time on Google Calendar](#block-focus-time) — Create recurring focus time blocks on Google Calendar to protect deep work hours.
- [Create Google Calendar Events from a Sheet](#create-events-from-sheet) — Read event data from a Google Sheets spreadsheet and create Google Calendar entries for each row.
- [Find Free Time Across Calendars](#find-free-time) — Query Google Calendar free/busy status for multiple users to find a meeting slot.
- [Plan Your Weekly Google Calendar Schedule](#plan-weekly-schedule) — Review your Google Calendar week, identify gaps, and add events to fill them.
- [Reschedule a Google Calendar Meeting](#reschedule-meeting) — Move a Google Calendar event to a new time and automatically notify all attendees.
- [Schedule a Recurring Meeting](#schedule-recurring-event) — Create a recurring Google Calendar event with attendees.
- [Share Files with Meeting Attendees](#share-event-materials) — Share Google Drive files with all attendees of a Google Calendar event.

### Docs & Sheets
- [Check Form Responses](#collect-form-responses) — Retrieve and review responses from a Google Form.
- [Compare Two Google Sheets Tabs](#compare-sheet-tabs) — Read data from two tabs in a Google Sheet to compare and identify differences.
- [Copy a Google Sheet for a New Month](#copy-sheet-for-new-month) — Duplicate a Google Sheets template tab for a new month of tracking.
- [Create a Google Doc from a Template](#create-doc-from-template) — Copy a Google Docs template, fill in content, and share with collaborators.
- [Create and Share a Google Form](#create-feedback-form) — Create a Google Form for feedback and share it via Gmail.
- [Create a Google Slides Presentation](#create-presentation) — Create a new Google Slides presentation and add initial slides.
- [Generate a Google Docs Report from Sheet Data](#generate-report-from-sheet) — Read data from a Google Sheet and create a formatted Google Docs report.
- [Share a Google Doc and Notify Collaborators](#share-doc-and-notify) — Share a Google Docs document with edit access and email collaborators the link.
- [Export Google Contacts to Sheets](#sync-contacts-to-sheet) — Export Google Contacts directory to a Google Sheets spreadsheet.

### Meet & Chat
- [Create a Google Meet Conference](#create-meet-space) — Create a Google Meet meeting space and share the join link.
- [Review Google Meet Attendance](#review-meet-participants) — Review who attended a Google Meet conference and for how long.
- [Announce via Gmail and Google Chat](#send-team-announcement) — Send a team announcement via both Gmail and a Google Chat space.

### Tasks & Planning
- [Create a Task List and Add Tasks](#create-task-list) — Set up a new Google Tasks list with initial tasks.
- [Review Overdue Tasks](#review-overdue-tasks) — Find Google Tasks that are past due and need attention.

### Other
- [Create a Google Classroom Course](#create-classroom-course) — Create a Google Classroom course and invite students.
- [Create a Google Sheets Expense Tracker](#create-expense-tracker) — Set up a Google Sheets spreadsheet for tracking expenses with headers and initial entries.
- [Log Deal Update to Sheet](#log-deal-update) — Append a deal status update to a Google Sheets sales tracking spreadsheet.
- [Set Up Post-Mortem](#post-mortem-setup) — Create a Google Docs post-mortem, schedule a Google Calendar review, and notify via Chat.

---

## Email & Gmail

### Create a Gmail Filter {#create-gmail-filter}

*Create a Gmail filter to automatically label, star, or categorize incoming messages.*

**Requires:** `gws-gmail`

## Steps

1. List existing labels: `gws gmail users labels list --params '{"userId": "me"}' --format table`
2. Create a new label: `gws gmail users labels create --params '{"userId": "me"}' --json '{"name": "Receipts"}'`
3. Create a filter: `gws gmail users settings filters create --params '{"userId": "me"}' --json '{"criteria": {"from": "receipts@example.com"}, "action": {"addLabelIds": ["LABEL_ID"], "removeLabelIds": ["INBOX"]}}'`
4. Verify filter: `gws gmail users settings filters list --params '{"userId": "me"}' --format table`

---

### Set Up a Gmail Vacation Responder {#create-vacation-responder}

*Enable a Gmail out-of-office auto-reply with a custom message and date range.*

**Requires:** `gws-gmail`

## Steps

1. Enable vacation responder: `gws gmail users settings updateVacation --params '{"userId": "me"}' --json '{"enableAutoReply": true, "responseSubject": "Out of Office", "responseBodyPlainText": "I am out of the office until Jan 20. For urgent matters, contact backup@company.com.", "restrictToContacts": false, "restrictToDomain": false}'`
2. Verify settings: `gws gmail users settings getVacation --params '{"userId": "me"}'`
3. Disable when back: `gws gmail users settings updateVacation --params '{"userId": "me"}' --json '{"enableAutoReply": false}'`

---

### Draft a Gmail Message from a Google Doc {#draft-email-from-doc}

*Read content from a Google Doc and use it as the body of a Gmail message.*

**Requires:** `gws-docs`, `gws-gmail`

## Steps

1. Get the document content: `gws docs documents get --params '{"documentId": "DOC_ID"}'`
2. Copy the text from the body content
3. Send the email: `gws gmail +send --to recipient@example.com --subject 'Newsletter Update' --body 'CONTENT_FROM_DOC'`

---

### Email a Google Drive File Link {#email-drive-link}

*Share a Google Drive file and email the link with a message to recipients.*

**Requires:** `gws-drive`, `gws-gmail`

## Steps

1. Find the file: `gws drive files list --params '{"q": "name = '\''Quarterly Report'\''"}'`
2. Share the file: `gws drive permissions create --params '{"fileId": "FILE_ID"}' --json '{"role": "reader", "type": "user", "emailAddress": "client@example.com"}'`
3. Email the link: `gws gmail +send --to client@example.com --subject 'Quarterly Report' --body 'Hi, please find the report here: https://docs.google.com/document/d/FILE_ID'`

---

### Forward Labeled Gmail Messages {#forward-labeled-emails}

*Find Gmail messages with a specific label and forward them to another address.*

**Requires:** `gws-gmail`

## Steps

1. Find labeled messages: `gws gmail users messages list --params '{"userId": "me", "q": "label:needs-review"}' --format table`
2. Get message content: `gws gmail users messages get --params '{"userId": "me", "id": "MSG_ID"}'`
3. Forward via new email: `gws gmail +send --to manager@company.com --subject 'FW: [Original Subject]' --body 'Forwarding for your review:

[Original Message Body]'`

---

### Label and Archive Gmail Threads {#label-and-archive-emails}

*Apply Gmail labels to matching messages and archive them to keep your inbox clean.*

**Requires:** `gws-gmail`

## Steps

1. Search for matching emails: `gws gmail users messages list --params '{"userId": "me", "q": "from:notifications@service.com"}' --format table`
2. Apply a label: `gws gmail users messages modify --params '{"userId": "me", "id": "MESSAGE_ID"}' --json '{"addLabelIds": ["LABEL_ID"]}'`
3. Archive (remove from inbox): `gws gmail users messages modify --params '{"userId": "me", "id": "MESSAGE_ID"}' --json '{"removeLabelIds": ["INBOX"]}'`

---

### Save Gmail Attachments to Google Drive {#save-email-attachments}

*Find Gmail messages with attachments and save them to a Google Drive folder.*

**Requires:** `gws-gmail`, `gws-drive`

## Steps

1. Search for emails with attachments: `gws gmail users messages list --params '{"userId": "me", "q": "has:attachment from:client@example.com"}' --format table`
2. Get message details: `gws gmail users messages get --params '{"userId": "me", "id": "MESSAGE_ID"}'`
3. Download attachment: `gws gmail users messages attachments get --params '{"userId": "me", "messageId": "MESSAGE_ID", "id": "ATTACHMENT_ID"}'`
4. Upload to Drive folder: `gws drive +upload --file ./attachment.pdf --parent FOLDER_ID`

---

### Save a Gmail Message to Google Docs {#save-email-to-doc}

*Save a Gmail message body into a Google Doc for archival or reference.*

**Requires:** `gws-gmail`, `gws-docs`

## Steps

1. Find the message: `gws gmail users messages list --params '{"userId": "me", "q": "subject:important from:boss@company.com"}' --format table`
2. Get message content: `gws gmail users messages get --params '{"userId": "me", "id": "MSG_ID"}'`
3. Create a doc with the content: `gws docs documents create --json '{"title": "Saved Email - Important Update"}'`
4. Write the email body: `gws docs +write --document-id DOC_ID --text 'From: boss@company.com
Subject: Important Update

[EMAIL BODY]'`

---

## Drive & Files

### Export a Google Sheet as CSV {#backup-sheet-as-csv}

*Export a Google Sheets spreadsheet as a CSV file for local backup or processing.*

**Requires:** `gws-sheets`, `gws-drive`

## Steps

1. Get spreadsheet details: `gws sheets spreadsheets get --params '{"spreadsheetId": "SHEET_ID"}'`
2. Export as CSV: `gws drive files export --params '{"fileId": "SHEET_ID", "mimeType": "text/csv"}'`
3. Or read values directly: `gws sheets +read --spreadsheet SHEET_ID --range 'Sheet1' --format csv`

---

### Bulk Download Drive Folder {#bulk-download-folder}

*List and download all files from a Google Drive folder.*

**Requires:** `gws-drive`

## Steps

1. List files in folder: `gws drive files list --params '{"q": "'\''FOLDER_ID'\'' in parents"}' --format json`
2. Download each file: `gws drive files get --params '{"fileId": "FILE_ID", "alt": "media"}' -o filename.ext`
3. Export Google Docs as PDF: `gws drive files export --params '{"fileId": "FILE_ID", "mimeType": "application/pdf"}' -o document.pdf`

---

### Create and Configure a Shared Drive {#create-shared-drive}

*Create a Google Shared Drive and add members with appropriate roles.*

**Requires:** `gws-drive`

## Steps

1. Create shared drive: `gws drive drives create --params '{"requestId": "unique-id-123"}' --json '{"name": "Project X"}'`
2. Add a member: `gws drive permissions create --params '{"fileId": "DRIVE_ID", "supportsAllDrives": true}' --json '{"role": "writer", "type": "user", "emailAddress": "member@company.com"}'`
3. List members: `gws drive permissions list --params '{"fileId": "DRIVE_ID", "supportsAllDrives": true}'`

---

### Find Largest Files in Drive {#find-large-files}

*Identify large Google Drive files consuming storage quota.*

**Requires:** `gws-drive`

## Steps

1. List files sorted by size: `gws drive files list --params '{"orderBy": "quotaBytesUsed desc", "pageSize": 20, "fields": "files(id,name,size,mimeType,owners)"}' --format table`
2. Review the output and identify files to archive or move

---

### Organize Files into Google Drive Folders {#organize-drive-folder}

*Create a Google Drive folder structure and move files into the right locations.*

**Requires:** `gws-drive`

## Steps

1. Create a project folder: `gws drive files create --json '{"name": "Q2 Project", "mimeType": "application/vnd.google-apps.folder"}'`
2. Create sub-folders: `gws drive files create --json '{"name": "Documents", "mimeType": "application/vnd.google-apps.folder", "parents": ["PARENT_FOLDER_ID"]}'`
3. Move existing files into folder: `gws drive files update --params '{"fileId": "FILE_ID", "addParents": "FOLDER_ID", "removeParents": "OLD_PARENT_ID"}'`
4. Verify structure: `gws drive files list --params '{"q": "FOLDER_ID in parents"}' --format table`

---

### Share a Google Drive Folder with a Team {#share-folder-with-team}

*Share a Google Drive folder and all its contents with a list of collaborators.*

**Requires:** `gws-drive`

## Steps

1. Find the folder: `gws drive files list --params '{"q": "name = '\''Project X'\'' and mimeType = '\''application/vnd.google-apps.folder'\''"}'`
2. Share as editor: `gws drive permissions create --params '{"fileId": "FOLDER_ID"}' --json '{"role": "writer", "type": "user", "emailAddress": "colleague@company.com"}'`
3. Share as viewer: `gws drive permissions create --params '{"fileId": "FOLDER_ID"}' --json '{"role": "reader", "type": "user", "emailAddress": "stakeholder@company.com"}'`
4. Verify permissions: `gws drive permissions list --params '{"fileId": "FOLDER_ID"}' --format table`

---

### Watch for Drive Changes {#watch-drive-changes}

*Subscribe to change notifications on a Google Drive file or folder.*

**Requires:** `gws-events`

## Steps

1. Create subscription: `gws events subscriptions create --json '{"targetResource": "//drive.googleapis.com/drives/DRIVE_ID", "eventTypes": ["google.workspace.drive.file.v1.updated"], "notificationEndpoint": {"pubsubTopic": "projects/PROJECT/topics/TOPIC"}, "payloadOptions": {"includeResource": true}}'`
2. List active subscriptions: `gws events subscriptions list`
3. Renew before expiry: `gws events +renew --subscription SUBSCRIPTION_ID`

---

## Calendar & Events

### Add Multiple Attendees to a Calendar Event {#batch-invite-to-event}

*Add a list of attendees to an existing Google Calendar event and send notifications.*

**Requires:** `gws-calendar`

## Steps

1. Get the event: `gws calendar events get --params '{"calendarId": "primary", "eventId": "EVENT_ID"}'`
2. Add attendees: `gws calendar events patch --params '{"calendarId": "primary", "eventId": "EVENT_ID", "sendUpdates": "all"}' --json '{"attendees": [{"email": "alice@company.com"}, {"email": "bob@company.com"}, {"email": "carol@company.com"}]}'`
3. Verify attendees: `gws calendar events get --params '{"calendarId": "primary", "eventId": "EVENT_ID"}'`

---

### Block Focus Time on Google Calendar {#block-focus-time}

*Create recurring focus time blocks on Google Calendar to protect deep work hours.*

**Requires:** `gws-calendar`

## Steps

1. Create recurring focus block: `gws calendar events insert --params '{"calendarId": "primary"}' --json '{"summary": "Focus Time", "description": "Protected deep work block", "start": {"dateTime": "2025-01-20T09:00:00", "timeZone": "America/New_York"}, "end": {"dateTime": "2025-01-20T11:00:00", "timeZone": "America/New_York"}, "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"], "transparency": "opaque"}'`
2. Verify it shows as busy: `gws calendar +agenda`

---

### Create Google Calendar Events from a Sheet {#create-events-from-sheet}

*Read event data from a Google Sheets spreadsheet and create Google Calendar entries for each row.*

**Requires:** `gws-sheets`, `gws-calendar`

## Steps

1. Read event data: `gws sheets +read --spreadsheet SHEET_ID --range "Events!A2:D"`
2. For each row, create a calendar event: `gws calendar +insert --summary 'Team Standup' --start '2026-01-20T09:00:00' --end '2026-01-20T09:30:00' --attendee alice@company.com --attendee bob@company.com`

---

### Find Free Time Across Calendars {#find-free-time}

*Query Google Calendar free/busy status for multiple users to find a meeting slot.*

**Requires:** `gws-calendar`

## Steps

1. Query free/busy: `gws calendar freebusy query --json '{"timeMin": "2024-03-18T08:00:00Z", "timeMax": "2024-03-18T18:00:00Z", "items": [{"id": "user1@company.com"}, {"id": "user2@company.com"}]}'`
2. Review the output to find overlapping free slots
3. Create event in the free slot: `gws calendar +insert --summary 'Meeting' --attendee user1@company.com --attendee user2@company.com --start '2024-03-18T14:00:00' --end '2024-03-18T14:30:00'`

---

### Plan Your Weekly Google Calendar Schedule {#plan-weekly-schedule}

*Review your Google Calendar week, identify gaps, and add events to fill them.*

**Requires:** `gws-calendar`

## Steps

1. Check this week's agenda: `gws calendar +agenda`
2. Check free/busy for the week: `gws calendar freebusy query --json '{"timeMin": "2025-01-20T00:00:00Z", "timeMax": "2025-01-25T00:00:00Z", "items": [{"id": "primary"}]}'`
3. Add a new event: `gws calendar +insert --summary 'Deep Work Block' --start '2026-01-21T14:00:00' --end '2026-01-21T16:00:00'`
4. Review updated schedule: `gws calendar +agenda`

---

### Reschedule a Google Calendar Meeting {#reschedule-meeting}

*Move a Google Calendar event to a new time and automatically notify all attendees.*

**Requires:** `gws-calendar`

## Steps

1. Find the event: `gws calendar +agenda`
2. Get event details: `gws calendar events get --params '{"calendarId": "primary", "eventId": "EVENT_ID"}'`
3. Update the time: `gws calendar events patch --params '{"calendarId": "primary", "eventId": "EVENT_ID", "sendUpdates": "all"}' --json '{"start": {"dateTime": "2025-01-22T14:00:00", "timeZone": "America/New_York"}, "end": {"dateTime": "2025-01-22T15:00:00", "timeZone": "America/New_York"}}'`

---

### Schedule a Recurring Meeting {#schedule-recurring-event}

*Create a recurring Google Calendar event with attendees.*

**Requires:** `gws-calendar`

## Steps

1. Create recurring event: `gws calendar events insert --params '{"calendarId": "primary"}' --json '{"summary": "Weekly Standup", "start": {"dateTime": "2024-03-18T09:00:00", "timeZone": "America/New_York"}, "end": {"dateTime": "2024-03-18T09:30:00", "timeZone": "America/New_York"}, "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO"], "attendees": [{"email": "team@company.com"}]}'`
2. Verify it was created: `gws calendar +agenda --days 14 --format table`

---

### Share Files with Meeting Attendees {#share-event-materials}

*Share Google Drive files with all attendees of a Google Calendar event.*

**Requires:** `gws-calendar`, `gws-drive`

## Steps

1. Get event attendees: `gws calendar events get --params '{"calendarId": "primary", "eventId": "EVENT_ID"}'`
2. Share file with each attendee: `gws drive permissions create --params '{"fileId": "FILE_ID"}' --json '{"role": "reader", "type": "user", "emailAddress": "attendee@company.com"}'`
3. Verify sharing: `gws drive permissions list --params '{"fileId": "FILE_ID"}' --format table`

---

## Docs & Sheets

### Check Form Responses {#collect-form-responses}

*Retrieve and review responses from a Google Form.*

**Requires:** `gws-forms`

## Steps

1. List forms: `gws forms forms list` (if you don't have the form ID)
2. Get form details: `gws forms forms get --params '{"formId": "FORM_ID"}'`
3. Get responses: `gws forms forms responses list --params '{"formId": "FORM_ID"}' --format table`

---

### Compare Two Google Sheets Tabs {#compare-sheet-tabs}

*Read data from two tabs in a Google Sheet to compare and identify differences.*

**Requires:** `gws-sheets`

## Steps

1. Read the first tab: `gws sheets +read --spreadsheet SHEET_ID --range "January!A1:D"`
2. Read the second tab: `gws sheets +read --spreadsheet SHEET_ID --range "February!A1:D"`
3. Compare the data and identify changes

---

### Copy a Google Sheet for a New Month {#copy-sheet-for-new-month}

*Duplicate a Google Sheets template tab for a new month of tracking.*

**Requires:** `gws-sheets`

## Steps

1. Get spreadsheet details: `gws sheets spreadsheets get --params '{"spreadsheetId": "SHEET_ID"}'`
2. Copy the template sheet: `gws sheets spreadsheets sheets copyTo --params '{"spreadsheetId": "SHEET_ID", "sheetId": 0}' --json '{"destinationSpreadsheetId": "SHEET_ID"}'`
3. Rename the new tab: `gws sheets spreadsheets batchUpdate --params '{"spreadsheetId": "SHEET_ID"}' --json '{"requests": [{"updateSheetProperties": {"properties": {"sheetId": 123, "title": "February 2025"}, "fields": "title"}}]}'`

---

### Create a Google Doc from a Template {#create-doc-from-template}

*Copy a Google Docs template, fill in content, and share with collaborators.*

**Requires:** `gws-drive`, `gws-docs`

## Steps

1. Copy the template: `gws drive files copy --params '{"fileId": "TEMPLATE_DOC_ID"}' --json '{"name": "Project Brief - Q2 Launch"}'`
2. Get the new doc ID from the response
3. Add content: `gws docs +write --document-id NEW_DOC_ID --text '## Project: Q2 Launch

### Objective
Launch the new feature by end of Q2.'`
4. Share with team: `gws drive permissions create --params '{"fileId": "NEW_DOC_ID"}' --json '{"role": "writer", "type": "user", "emailAddress": "team@company.com"}'`

---

### Create and Share a Google Form {#create-feedback-form}

*Create a Google Form for feedback and share it via Gmail.*

**Requires:** `gws-forms`, `gws-gmail`

## Steps

1. Create form: `gws forms forms create --json '{"info": {"title": "Event Feedback", "documentTitle": "Event Feedback Form"}}'`
2. Get the form URL from the response (responderUri field)
3. Email the form: `gws gmail +send --to attendees@company.com --subject 'Please share your feedback' --body 'Fill out the form: FORM_URL'`

---

### Create a Google Slides Presentation {#create-presentation}

*Create a new Google Slides presentation and add initial slides.*

**Requires:** `gws-slides`

## Steps

1. Create presentation: `gws slides presentations create --json '{"title": "Quarterly Review Q2"}'`
2. Get the presentation ID from the response
3. Share with team: `gws drive permissions create --params '{"fileId": "PRESENTATION_ID"}' --json '{"role": "writer", "type": "user", "emailAddress": "team@company.com"}'`

---

### Generate a Google Docs Report from Sheet Data {#generate-report-from-sheet}

*Read data from a Google Sheet and create a formatted Google Docs report.*

**Requires:** `gws-sheets`, `gws-docs`, `gws-drive`

## Steps

1. Read the data: `gws sheets +read --spreadsheet SHEET_ID --range "Sales!A1:D"`
2. Create the report doc: `gws docs documents create --json '{"title": "Sales Report - January 2025"}'`
3. Write the report: `gws docs +write --document-id DOC_ID --text '## Sales Report - January 2025

### Summary
Total deals: 45
Revenue: $125,000

### Top Deals
1. Acme Corp - $25,000
2. Widget Inc - $18,000'`
4. Share with stakeholders: `gws drive permissions create --params '{"fileId": "DOC_ID"}' --json '{"role": "reader", "type": "user", "emailAddress": "cfo@company.com"}'`

---

### Share a Google Doc and Notify Collaborators {#share-doc-and-notify}

*Share a Google Docs document with edit access and email collaborators the link.*

**Requires:** `gws-drive`, `gws-docs`, `gws-gmail`

## Steps

1. Find the doc: `gws drive files list --params '{"q": "name contains '\''Project Brief'\'' and mimeType = '\''application/vnd.google-apps.document'\''"}'`
2. Share with editor access: `gws drive permissions create --params '{"fileId": "DOC_ID"}' --json '{"role": "writer", "type": "user", "emailAddress": "reviewer@company.com"}'`
3. Email the link: `gws gmail +send --to reviewer@company.com --subject 'Please review: Project Brief' --body 'I have shared the project brief with you: https://docs.google.com/document/d/DOC_ID'`

---

### Export Google Contacts to Sheets {#sync-contacts-to-sheet}

*Export Google Contacts directory to a Google Sheets spreadsheet.*

**Requires:** `gws-people`, `gws-sheets`

## Steps

1. List contacts: `gws people people listDirectoryPeople --params '{"readMask": "names,emailAddresses,phoneNumbers", "sources": ["DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE"], "pageSize": 100}' --format json`
2. Create a sheet: `gws sheets +append --spreadsheet SHEET_ID --range 'Contacts' --values '["Name", "Email", "Phone"]'`
3. Append each contact row: `gws sheets +append --spreadsheet SHEET_ID --range 'Contacts' --values '["Jane Doe", "jane@company.com", "+1-555-0100"]'`

---

## Meet & Chat

### Create a Google Meet Conference {#create-meet-space}

*Create a Google Meet meeting space and share the join link.*

**Requires:** `gws-meet`, `gws-gmail`

## Steps

1. Create meeting space: `gws meet spaces create --json '{"config": {"accessType": "OPEN"}}'`
2. Copy the meeting URI from the response
3. Email the link: `gws gmail +send --to team@company.com --subject 'Join the meeting' --body 'Join here: MEETING_URI'`

---

### Review Google Meet Attendance {#review-meet-participants}

*Review who attended a Google Meet conference and for how long.*

**Requires:** `gws-meet`

## Steps

1. List recent conferences: `gws meet conferenceRecords list --format table`
2. List participants: `gws meet conferenceRecords participants list --params '{"parent": "conferenceRecords/CONFERENCE_ID"}' --format table`
3. Get session details: `gws meet conferenceRecords participants participantSessions list --params '{"parent": "conferenceRecords/CONFERENCE_ID/participants/PARTICIPANT_ID"}' --format table`

---

### Announce via Gmail and Google Chat {#send-team-announcement}

*Send a team announcement via both Gmail and a Google Chat space.*

**Requires:** `gws-gmail`, `gws-chat`

## Steps

1. Send email: `gws gmail +send --to team@company.com --subject 'Important Update' --body 'Please review the attached policy changes.'`
2. Post in Chat: `gws chat +send --space spaces/TEAM_SPACE --text '📢 Important Update: Please check your email for policy changes.'`

---

## Tasks & Planning

### Create a Task List and Add Tasks {#create-task-list}

*Set up a new Google Tasks list with initial tasks.*

**Requires:** `gws-tasks`

## Steps

1. Create task list: `gws tasks tasklists insert --json '{"title": "Q2 Goals"}'`
2. Add a task: `gws tasks tasks insert --params '{"tasklist": "TASKLIST_ID"}' --json '{"title": "Review Q1 metrics", "notes": "Pull data from analytics dashboard", "due": "2024-04-01T00:00:00Z"}'`
3. Add another task: `gws tasks tasks insert --params '{"tasklist": "TASKLIST_ID"}' --json '{"title": "Draft Q2 OKRs"}'`
4. List tasks: `gws tasks tasks list --params '{"tasklist": "TASKLIST_ID"}' --format table`

---

### Review Overdue Tasks {#review-overdue-tasks}

*Find Google Tasks that are past due and need attention.*

**Requires:** `gws-tasks`

## Steps

1. List task lists: `gws tasks tasklists list --format table`
2. List tasks with status: `gws tasks tasks list --params '{"tasklist": "TASKLIST_ID", "showCompleted": false}' --format table`
3. Review due dates and prioritize overdue items

---

## Other

### Create a Google Classroom Course {#create-classroom-course}

*Create a Google Classroom course and invite students.*

**Requires:** `gws-classroom`

## Steps

1. Create the course: `gws classroom courses create --json '{"name": "Introduction to CS", "section": "Period 1", "room": "Room 101", "ownerId": "me"}'`
2. Invite a student: `gws classroom invitations create --json '{"courseId": "COURSE_ID", "userId": "student@school.edu", "role": "STUDENT"}'`
3. List enrolled students: `gws classroom courses students list --params '{"courseId": "COURSE_ID"}' --format table`

---

### Create a Google Sheets Expense Tracker {#create-expense-tracker}

*Set up a Google Sheets spreadsheet for tracking expenses with headers and initial entries.*

**Requires:** `gws-sheets`, `gws-drive`

## Steps

1. Create spreadsheet: `gws drive files create --json '{"name": "Expense Tracker 2025", "mimeType": "application/vnd.google-apps.spreadsheet"}'`
2. Add headers: `gws sheets +append --spreadsheet SHEET_ID --range 'Sheet1' --values '["Date", "Category", "Description", "Amount"]'`
3. Add first entry: `gws sheets +append --spreadsheet SHEET_ID --range 'Sheet1' --values '["2025-01-15", "Travel", "Flight to NYC", "450.00"]'`
4. Share with manager: `gws drive permissions create --params '{"fileId": "SHEET_ID"}' --json '{"role": "reader", "type": "user", "emailAddress": "manager@company.com"}'`

---

### Log Deal Update to Sheet {#log-deal-update}

*Append a deal status update to a Google Sheets sales tracking spreadsheet.*

**Requires:** `gws-sheets`, `gws-drive`

## Steps

1. Find the tracking sheet: `gws drive files list --params '{"q": "name = '\''Sales Pipeline'\'' and mimeType = '\''application/vnd.google-apps.spreadsheet'\''"}'`
2. Read current data: `gws sheets +read --spreadsheet SHEET_ID --range "Pipeline!A1:F"`
3. Append new row: `gws sheets +append --spreadsheet SHEET_ID --range 'Pipeline' --values '["2024-03-15", "Acme Corp", "Proposal Sent", "$50,000", "Q2", "jdoe"]'`

---

### Set Up Post-Mortem {#post-mortem-setup}

*Create a Google Docs post-mortem, schedule a Google Calendar review, and notify via Chat.*

**Requires:** `gws-docs`, `gws-calendar`, `gws-chat`

## Steps

1. Create post-mortem doc: `gws docs +write --title 'Post-Mortem: [Incident]' --body '## Summary\n\n## Timeline\n\n## Root Cause\n\n## Action Items'`
2. Schedule review meeting: `gws calendar +insert --summary 'Post-Mortem Review: [Incident]' --attendee team@company.com --start '2026-03-16T14:00:00' --end '2026-03-16T15:00:00'`
3. Notify in Chat: `gws chat +send --space spaces/ENG_SPACE --text '🔍 Post-mortem scheduled for [Incident].'`

---

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]] | [[skills/gws-shared/SKILL]]