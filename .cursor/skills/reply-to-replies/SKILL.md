---
name: reply-to-replies
description: Draft high-quality follow-up replies to inbound email responses by detecting intent, extracting asks, and generating concise response drafts. Use when the user wants to reply to recipient emails, handle objections, answer questions, schedule demos, or write next-step follow-ups.
---

# Reply To Inbound Emails

## Purpose

Generate a strong outbound reply after a recipient responds. Focus on clear next steps, low-friction asks, and natural tone.

This skill is independent of prior campaign scripts. Do not require `send_postmark.py`, `crm_check.py`, or any legacy workflow to produce reply drafts.

## Inputs To Request

Ask for only the minimum missing context:

1. Recipient reply text (full or key excerpt)
2. Original outreach context (1-2 sentences or original email)
3. Desired outcome (book call, answer question, re-engage, close loop)
4. Constraints (tone, language, response length, forbidden claims)

If any item is missing, ask concise questions before drafting.

## Reply Workflow

### Step 1: Identify intent

Classify the recipient reply into one primary intent:

- interested
- question
- concern
- pricing
- timing-later
- handoff
- rejection
- unsubscribe
- unclear

### Step 2: Extract action items

From the recipient reply, extract:

- explicit question(s)
- objection(s)
- decision signal (positive/neutral/negative)
- concrete next step requested (if any)

### Step 3: Build the response strategy

Use this mapping:

- interested -> confirm fit + propose 1 clear scheduling option
- question -> answer directly first, then invite next step
- concern -> acknowledge concern, give one concrete clarification
- pricing -> provide concise pricing frame or offer tailored quote path
- timing-later -> accept timing and set a light follow-up checkpoint
- handoff -> ask for best contact and include short forwardable blurb
- rejection -> polite close, optional door-open line
- unsubscribe -> confirm removal, no further pitch
- unclear -> ask one focused clarifying question

### Step 4: Write draft

Rules:

- Keep to 80-160 words unless user requests otherwise
- Match recipient language (English/Chinese) when possible
- One email, one core objective
- No exaggerated claims, no pressure language
- Include one clear CTA at most

## Output Format

Return in this structure:

```markdown
Intent: <one label>

Why:
- <one-line reason 1>
- <one-line reason 2>

Draft Reply:
<final email body>

Optional Subject:
<subject line if user asked>
```

## Draft Templates

### Interested

```text
Thanks for your reply, <Name> — glad this is relevant.

Given your workflow, I can show you a focused 15-minute walkthrough on <use case>.
Would <Option A> or <Option B> work better this week?

If easier, feel free to share your preferred time and I will adapt.
```

### Concern

```text
Thanks for raising this — great question.

Short answer: <direct clarification>.
In practice, teams use it to <specific outcome> without changing <existing process>.

If useful, I can send a 3-bullet comparison for your setup.
```

### Rejection

```text
Thanks for the quick response, <Name>.

Understood, and I appreciate the clarity. I will not follow up further.
If priorities change later, I am happy to reconnect.
```

## Guardrails

- If recipient asks to stop emails, always prioritize compliance response.
- Never fabricate product capabilities or customer references.
- If legal/security/compliance questions appear, provide a draft plus a "needs confirmation" note for the user.
- Do not auto-send; draft only unless user explicitly asks to send.
