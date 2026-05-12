"""CSV Validation Script — Steps 1-8"""
import pandas as pd
import re
import sys

csv_path = r"..\updated_attendance_with_may9.csv"
emp_path = r"..\employees_rows.csv"

df = pd.read_csv(csv_path)
emps = pd.read_csv(emp_path)

print("=" * 60)
print("STEP 1: STRUCTURE VALIDATION")
print("=" * 60)
cols = list(df.columns)
print(f"Columns found: {cols}")
required = ["email", "log_date", "first_in", "last_out", "status"]
missing = [c for c in required if c not in cols]
print(f"Missing required: {missing if missing else 'NONE'}")
print(f"Total rows: {len(df)}")
print(f"Result: {'PASS' if not missing else 'FAIL'}")
print()

print("=" * 60)
print("STEP 2: DATA TYPE VALIDATION")
print("=" * 60)

# Email
email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
bad_email_mask = ~df["email"].str.match(email_regex, na=False)
invalid_emails = df[bad_email_mask]
print(f"Invalid email format: {len(invalid_emails)} rows")
null_emails = df["email"].isna().sum()
print(f"Null emails: {null_emails}")

# log_date
null_dates = df["log_date"].isna().sum()
print(f"Null log_date: {null_dates}")
dates = pd.to_datetime(df["log_date"], errors="coerce")
bad_dates = dates.isna().sum()
print(f"Unparseable dates: {bad_dates}")
if bad_dates == 0:
    print(f"Date range: {dates.min().date()} to {dates.max().date()}")

# Status
valid_statuses = {"PRESENT", "ABSENT", "LATE", "HALF_DAY", "ON_LEAVE", "HOLIDAY", "WEEKEND"}
actual_statuses = set(df["status"].dropna().str.strip().str.upper().unique())
invalid_statuses = actual_statuses - valid_statuses
print(f"Status values: {sorted(actual_statuses)}")
print(f"Invalid statuses: {invalid_statuses if invalid_statuses else 'NONE'}")
null_status = df["status"].isna().sum()
print(f"Null statuses: {null_status}")

# Status distribution
print(f"\nStatus distribution:")
for s, c in df["status"].value_counts().items():
    print(f"  {s}: {c}")
print()

print("=" * 60)
print("STEP 3: BUSINESS RULES")
print("=" * 60)
holidays = df[df["status"].str.upper().isin(["HOLIDAY", "WEEKEND"])]
hol_with_in = holidays["first_in"].notna().sum()
hol_with_out = holidays["last_out"].notna().sum()
print(f"HOLIDAY/WEEKEND rows: {len(holidays)}")
print(f"  with first_in set: {hol_with_in}")
print(f"  with last_out set: {hol_with_out}")

present = df[df["status"].str.upper().isin(["PRESENT", "LATE"])]
pres_no_in = present["first_in"].isna().sum()
pres_no_out = present["last_out"].isna().sum()
print(f"PRESENT/LATE rows: {len(present)}")
print(f"  missing first_in: {pres_no_in}")
print(f"  missing last_out: {pres_no_out}")

absent = df[df["status"].str.upper().isin(["ABSENT", "ON_LEAVE"])]
print(f"ABSENT/ON_LEAVE rows: {len(absent)}")
print()

print("=" * 60)
print("STEP 4: EMPLOYEE MAPPING")
print("=" * 60)
db_emails = set(emps["email"].str.strip().str.lower())
csv_emails = set(df["email"].str.strip().str.lower().unique())
matched = csv_emails & db_emails
unmatched = csv_emails - db_emails
print(f"Unique emails in CSV: {len(csv_emails)}")
print(f"Emails in DB: {len(db_emails)}")
print(f"Matched: {len(matched)}")
print(f"Unmatched: {unmatched if unmatched else 'NONE'}")
print(f"Match rate: {len(matched)}/{len(csv_emails)} ({100*len(matched)//len(csv_emails)}%)")
print()

print("=" * 60)
print("STEP 5: DUPLICATE CHECK")
print("=" * 60)
dupes = df.duplicated(subset=["email", "log_date"], keep=False)
dupe_count = dupes.sum()
print(f"Duplicate (email, log_date) rows: {dupe_count}")
if dupe_count > 0:
    dupe_rows = df[dupes].sort_values(["email", "log_date"])
    print("Duplicate entries:")
    for _, row in dupe_rows.head(10).iterrows():
        print(f"  {row['email']} | {row['log_date']} | {row['status']}")
print()

print("=" * 60)
print("STEP 6: DRY RUN PARSE")
print("=" * 60)
sys.path.insert(0, ".")
from app.services.csv_parser import parse_attendance_file
content = open(csv_path, "rb").read()
records, errors = parse_attendance_file(content, "updated_attendance_with_may9.csv")
print(f"Parsed records: {len(records)}")
print(f"Parse errors: {len(errors)}")
if errors:
    print("First 5 errors:")
    for e in errors[:5]:
        print(f"  Row {e.row}: {e.message}")

# Check computed statuses
status_dist = {}
for r in records:
    s = r.computed_status
    status_dist[s] = status_dist.get(s, 0) + 1
print(f"Computed status distribution: {status_dist}")

# Check holiday handling
hol_records = [r for r in records if r.computed_status in ("HOLIDAY", "WEEKEND")]
hol_null_in = sum(1 for r in hol_records if r.first_in is None)
print(f"HOLIDAY records with null first_in: {hol_null_in}/{len(hol_records)}")
print()

print("=" * 60)
print("STEP 7: FAILURE POINTS")
print("=" * 60)
issues = []
if missing:
    issues.append(f"Missing columns: {missing}")
if invalid_statuses:
    issues.append(f"Invalid statuses: {invalid_statuses}")
if unmatched:
    issues.append(f"Unmatched emails: {unmatched}")
if dupe_count > 0:
    issues.append(f"{dupe_count} duplicate (email, log_date) rows (UPSERT-safe)")
if pres_no_in > 0:
    issues.append(f"{pres_no_in} PRESENT/LATE rows missing first_in")
if pres_no_out > 0:
    issues.append(f"{pres_no_out} PRESENT/LATE rows missing last_out")
if len(errors) > 0:
    issues.append(f"{len(errors)} parse errors")

if not issues:
    print("No issues found!")
else:
    for i in issues:
        print(f"  - {i}")
print()

print("=" * 60)
print("STEP 8: FINAL VERDICT")
print("=" * 60)
blockers = [i for i in issues if "Unmatched" in i or "Missing columns" in i or "Invalid statuses" in i or "parse errors" in i]
if not blockers:
    print("VERDICT: VALID - safe to upload")
else:
    print("VERDICT: INVALID - fixes required:")
    for b in blockers:
        print(f"  {b}")
