#!/usr/bin/env python3
"""One-off: expand sandbox/ with a large messy test tree. Safe to re-run (adds/overwrites these paths)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "sandbox"


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    files["00_INBOX/readme_FIRST.txt"] = """
INBOX — stuff I will sort later
- call dentist
- fix scanner
Last updated: who knows
"""

    files["00_INBOX/FW_ Contract review - urgent!!.txt"] = """
Forwarded message
Can someone look at section 4? Client waiting.
Attachments were lost in email chain.
"""

    files["Desktop_dump/shortcut_targets.txt"] = """
Links I saved and never opened
- proposal_draft somewhere in downloads?
- shared drive: \\\\fake\\team\\2024
"""

    files["Desktop_dump/passwords_DO_NOT_USE.txt"] = """
FAKE PLACEHOLDER — not real secrets
Use a password manager. This file should be deleted.
"""

    files["Downloads/(1) signed_copy maybe.pdf.txt"] = """
Renamed from email — actually plain text export
Agreement between parties regarding services Q3.
Status: unclear if fully executed.
"""

    files["Downloads/chromewebdata_random.html.txt"] = """
Saved page snippet — meeting agenda
1. Budget 2. Hiring 3. Office move
"""

    files["Downloads/GitHub/issue_442_notes.txt"] = """
Bug: export fails on Windows paths with spaces
Repro: use folder "my files"
"""

    files["Finances/2023/old_bank_export.csv"] = """
date,desc,amount
2023-11-02,COFFEE SHOP,-4.50
2023-11-03,DEPOSIT PAYROLL,2400.00
2023-12-01,AMAZON *MKTPLACE,-89.99
"""

    files["Finances/2024/personal/grocery_estimates.txt"] = """
Rough monthly food ~600
Costco run 1st week, farmers market Sundays
"""

    files["Finances/2024/biz_expenses_draft.txt"] = """
Needs categorization
- software subscriptions
- client lunch 3/14 (receipt in phone photos?)
"""

    files["Finances/misc/INVOICE copy copy.txt"] = """
Duplicate filename nightmare
Amount due: 1200
Project: Website maintenance
"""

    files["HR/onboarding_checklist_v3_FINAL.txt"] = """
New hire — Riverside project
[ ] Laptop
[ ] Badge
[ ] NDA signed (see Legal folder?)
"""

    files["HR/pto_requests_2024.txt"] = """
Jan 15-19 — PTO Jah
Mar 4 — half day dentist
"""

    files["Legal/NDA_templates/mutual_nda_blank.txt"] = """
MUTUAL NON-DISCLOSURE AGREEMENT
Parties: _________ and _________
Term: 2 years
[template — fill before use]
"""

    files["Legal/NDA_templates/one_way_vendor.txt"] = """
Vendor NDA — one directional
Review with counsel before sending.
"""

    files["Legal/disputes/notes_timeline.txt"] = """
Chronology (internal)
- Feb: initial complaint
- Mar: mediation scheduled
Do not share externally.
"""

    files["Meetings/2024-01-15 standup.txt"] = """
Attendees: A, B, C
Blockers: waiting on API keys
Next: demo Friday
"""

    files["Meetings/2024-03-22 client call - ACME.txt"] = """
ACME corp — wants folder structure by department
They have 400+ loose PDFs in a shared drive
"""

    files["Meetings/NO_DATE_transcript_fragment.txt"] = """
...and then she said we should organize by client first...
[partial notes]
"""

    files["Photos_from_phone/receipt_20240302_coffee.jpg.txt"] = """
(This is a text stand-in for a receipt image)
Merchant: Morning Brew
Total: 7.42
"""

    files["Photos_from_phone/IMG_9931_unknown.txt"] = """
Whiteboard photo — illegible
Maybe Q2 roadmap?
"""

    files["Projects/Riverside/status.txt"] = """
Riverside engagement — active
Key contact: ops@riverside.example
"""

    files["Projects/Riverside/deliverables/phase1_outline.md"] = """
# Phase 1
- Discovery
- File inventory
- Proposed taxonomy
"""

    files["Projects/side_project_idea/README.txt"] = """
Automate invoice renaming using date + vendor
Never started — low priority
"""

    files["Receipts/2024/March/amazon_order_8821.txt"] = """
Order #8821
Office supplies — toner, cables
Total 156.88
"""

    files["Receipts/2024/March/uber_trip_client_dinner.txt"] = """
Ride to downtown — client dinner
Amount 24.10 — billable?
"""

    files["Receipts/unsorted/receipt.txt"] = """
Generic receipt — no date
Items: lunch x3
"""

    files["Receipts/unsorted/receipt (1).txt"] = """
Another generic receipt
Total 42.00
"""

    files["Shared_with_me/TeamDrive_export_list.txt"] = """
Files pulled from shared drive (names only)
report_final.pdf
report_final_v2.pdf
report_final_REALLY_FINAL.pdf
"""

    files["Temp/delete_me_later/cache_list.txt"] = """
Temp exports — safe to purge?
export_tmp_001.csv
export_tmp_002.csv
"""

    files["Temp/zzz_old_builds/build_log_snippet.txt"] = """
[WARN] path too long
[OK] module core
"""

    files["Vendors/ACME/contact_sheet.txt"] = """
ACME Corp
AP: ap@acme.example
Primary: j.smith@acme.example
"""

    files["Vendors/Northside_LLC/contract_summary.txt"] = """
Northside — maintenance agreement renewed annually
Renewal month: June
"""

    files["Vendors/random_vendor/quote_#774.txt"] = """
Quote #774 — landscaping
Valid 30 days
"""

    files["__OLD_BACKUP/2019/tax_stuff/notes.txt"] = """
Old archive — do not mix with 2024 taxes
"""

    files["client work MIXED CASE/Riverside/random_note.txt"] = """
Call back about engagement letter edits
"""

    files["client work MIXED CASE/acme/TODO_acme.txt"] = """
Follow up on unsigned NDA
"""

    files["documents (no really)/thing.txt"] = """
I put documents here to hide them from search
Actually just notes.
"""

    files["folder with spaces (messy)/nested/file inside.txt"] = """
Nested under awkwardly named parent folder
Content: nothing important
"""

    files["logs/app.2024-03-01.log"] = """
INFO boot
WARN slow query 1200ms
ERROR timeout contacting vendor API
"""

    files["logs/scanner_error.log"] = """
Paper jam tray 2
Calibration failed
"""

    files["new folder (2)/empty_parent_readme.txt"] = """
This folder was auto-created by Windows
"""

    files["stuff/more_stuff/even_more/deep_file.txt"] = """
Deep nesting test
Invoice ref: INV-2024-0099
"""

    files["taxes/2022/W2_placeholder.txt"] = """
Placeholder — replace with real forms
"""

    files["taxes/2024/WORK_IN_PROGRESS.txt"] = """
Gather:
- 1099s
- mortgage interest
Receipts scattered in Downloads and Photos
"""

    files["video_projects/b_roll_list.txt"] = """
Clips to organize by shoot date
clip_a.mov
clip_a_copy.mov
clip_a_final.mov
"""

    files["website_assets/logo_variants/README.txt"] = """
logo.png logo_white.png logo_bw.png — which is canonical?
"""

    files["z_Archive_SORT_ME/misc_junk.txt"] = """
Everything dumped here during office move
"""

    files["Contracts/amendment_draft_v1.txt"] = """
DRAFT amendment to master services agreement
Not signed — compare with executed master in filing cabinet
"""

    files["Contracts/SOW_website_refresh_unsigned.txt"] = """
Statement of Work — Website refresh
Total not to exceed 25k
Signatures: pending
"""

    files["Invoices/INV-2024-0042_client_unknown.txt"] = """
Invoice 0042
Line items unclear — verify against contract
Amount: 3300.00
"""

    files["Invoices/duplicate_name/invoice_march.txt"] = """
March services — version A
"""

    files["Invoices/duplicate_name/sub/invoice_march.txt"] = """
March services — version B (wrong folder?)
"""

    files["Downloads/draft_service_agreement_SUPPLEMENT.txt"] = """
Supplemental draft notes (separate from original draft_service_agreement.txt)
Addendum: SLA section pending legal review
"""

    files["email_exports/2024-Q1/thread_fragment.txt"] = """
From: client@example.com
Subject: RE: RE: RE: files
We still can't find the signed copy.
"""

    files["email_exports/misc/UNREAD_import.txt"] = """
Exported 200 messages — none labeled
"""

    files["Kids_school/forms/field_trip_maybe_signed.txt"] = """
Field trip permission — signature line: SMUDGE
Date: illegible
"""

    files["Medical/refill_reminder.txt"] = """
Pharmacy auto-refill on file
NOT REAL PHI — synthetic test data
"""

    files["Quotes/estimate_roof_repair.txt"] = """
Ballpark 8-12k — waiting on second quote
"""

    files["Quotes/estimate_roof_repair_REVISED.txt"] = """
Revised 9-14k after inspection
"""

    files["Spreadsheets/employee_list_OLD_DO_NOT_USE.csv"] = """
name,role,email
Alice,Dev,alice@example.com
Bob,Ops,bob@example.com
"""

    files["Spreadsheets/mystery_tab_export.tsv"] = """
colA	colB	colC
1	2	3
foo	bar	baz
"""

    files["Training/certificates/placeholder_completed.txt"] = """
Certificate of completion — Cybersecurity basics
Issued: synthetic
"""

    files["Whiteboards/photo_notes_transcribed_badly.txt"] = """
??? hire ??? budget ??? Q3
"""

    files["ZIPS (not zip)/contents_manifest.txt"] = """
Misleading folder name — these were never zipped
"""

    for rel, body in files.items():
        write(rel, body)

    print(f"Wrote {len(files)} text files under {ROOT}")


if __name__ == "__main__":
    main()
