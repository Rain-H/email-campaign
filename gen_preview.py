#!/usr/bin/env python3
import csv, json, re

with open("email-template-v5.md", encoding="utf-8") as f:
    raw = f.read().strip()

subject_line = re.search(r"^Subject:\s*(.+)$", raw, re.MULTILINE).group(1).strip()
body_template = raw.split("\n", 2)[2].strip()

def first_name(full):
    parts = full.strip().split()
    for p in parts:
        if p.rstrip('.').lower() not in {'dr', 'prof', 'assoc', 'ir', 'ts', 'mr', 'ms', 'mrs', 'sir', 'eng'}:
            return p
    return parts[-1] if parts else full

previews = []
with open("batch_500.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        name = row["chair_name"].strip()
        email = row["chair_email"].strip()
        conf = row["conference_short_name"].strip()

        subject = subject_line.replace("[Conference Name]", conf)
        body = body_template.replace("[Name]", first_name(name)).replace("[Conference Name]", conf)

        previews.append({
            "to": email,
            "name": name,
            "conference": conf,
            "subject": subject,
            "body": body,
        })

with open("email_preview.json", "w", encoding="utf-8") as f:
    json.dump(previews, f, ensure_ascii=False, indent=2)

print(f"已生成 email_preview.json，共 {len(previews)} 封\n")
print("前3封预览:")
for p in previews[:3]:
    print(f"\n--- To: {p['to']} ---")
    print(f"Subject: {p['subject']}")
    print(p['body'])
