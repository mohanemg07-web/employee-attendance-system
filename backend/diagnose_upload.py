"""Diagnostic: simulate the CSV upload pipeline step by step to find the crash."""
import asyncio
import sys
import traceback

sys.path.insert(0, ".")


async def diagnose():
    print("=" * 60)
    print("DIAGNOSTIC: CSV Upload Pipeline")
    print("=" * 60)

    csv_path = r"..\updated_attendance_with_may9.csv"

    # Step 1: Parse
    print("\n[1] Parsing CSV...")
    try:
        from app.services.csv_parser import parse_attendance_file
        content = open(csv_path, "rb").read()
        records, errors = parse_attendance_file(content, "test.csv")
        print(f"    PASS: {len(records)} records, {len(errors)} errors")
    except Exception as e:
        print(f"    FAIL: {e}")
        traceback.print_exc()
        return

    # Step 2: Check computed statuses
    print("\n[2] Checking computed statuses...")
    try:
        for r in records[:5]:
            s = r.computed_status
            print(f"    {r.email} | {r.log_date} | status={s} | first_in={r.first_in}")
        print(f"    PASS: All records have computed_status")
    except Exception as e:
        print(f"    FAIL: {e}")
        traceback.print_exc()
        return

    # Step 3: Check work hours computation
    print("\n[3] Checking work hours computation...")
    try:
        for r in records[:5]:
            wh = r.computed_work_hours_td
            print(f"    {r.email} | {r.log_date} | work_hrs={wh}")
        print(f"    PASS")
    except Exception as e:
        print(f"    FAIL: {e}")
        traceback.print_exc()
        return

    # Step 4: Test DB connection
    print("\n[4] Testing DB connection...")
    try:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            from sqlalchemy import text
            result = await db.execute(text("SELECT 1"))
            print(f"    PASS: DB connected")
    except Exception as e:
        print(f"    FAIL: {e}")
        traceback.print_exc()
        return

    # Step 5: Build employee maps
    print("\n[5] Building employee maps...")
    try:
        from app.database import AsyncSessionLocal
        from app.crud.crud_csv import _build_employee_maps
        async with AsyncSessionLocal() as db:
            code_map, email_map = await _build_employee_maps(db)
            print(f"    code_map: {len(code_map)} entries")
            print(f"    email_map: {len(email_map)} entries")
            if email_map:
                for email, eid in list(email_map.items())[:3]:
                    print(f"      {email} -> {eid}")
            print(f"    PASS")
    except Exception as e:
        print(f"    FAIL: {e}")
        traceback.print_exc()
        return

    # Step 6: Test matching
    print("\n[6] Testing email matching...")
    matched = 0
    unmatched = []
    for r in records:
        if r.email:
            eid = email_map.get(r.email.strip().lower())
            if eid:
                matched += 1
            else:
                if r.email not in unmatched:
                    unmatched.append(r.email)
    print(f"    Matched: {matched}/{len(records)}")
    if unmatched:
        print(f"    UNMATCHED: {unmatched}")
    else:
        print(f"    PASS: All emails matched")

    # Step 7: Test single record upsert
    print("\n[7] Testing single record upsert (DRY RUN)...")
    try:
        from app.crud.crud_csv import upsert_csv_record
        test_record = records[0]
        test_emp_id = email_map.get(test_record.email.strip().lower())
        print(f"    Record: {test_record.email} | {test_record.log_date} | status={test_record.computed_status}")
        print(f"    Employee ID: {test_emp_id}")
        # Actually try the upsert
        async with AsyncSessionLocal() as db:
            outcome = await upsert_csv_record(db, test_record, test_emp_id)
            print(f"    Outcome: {outcome}")
            await db.rollback()  # Don't persist
            print(f"    PASS (rolled back)")
    except Exception as e:
        print(f"    FAIL: {e}")
        traceback.print_exc()
        return

    # Step 8: Test audit_logs table
    print("\n[8] Testing audit_logs table...")
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import text
            result = await db.execute(text("SELECT count(*) FROM audit_logs"))
            count = result.scalar()
            print(f"    audit_logs rows: {count}")
            print(f"    PASS")
    except Exception as e:
        print(f"    FAIL: audit_logs table issue: {e}")
        print(f"    This would cause the upload to fail!")

    # Step 9: Test full batch (but rollback)
    print("\n[9] Testing full batch upsert...")
    try:
        from app.crud.crud_csv import upsert_csv_batch
        async with AsyncSessionLocal() as db:
            result = await upsert_csv_batch(db, records[:10], "test_10rows.csv")
            print(f"    inserted={result.inserted} updated={result.updated} errors={result.errors}")
            if result.error_messages:
                for msg in result.error_messages[:5]:
                    print(f"    ERROR: {msg}")
            await db.rollback()  # Don't persist
            print(f"    PASS (rolled back)")
    except Exception as e:
        print(f"    FAIL: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


asyncio.run(diagnose())
