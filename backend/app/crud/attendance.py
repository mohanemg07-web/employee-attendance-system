"""
Unified attendance CRUD facade.

Re-exports daily and monthly attendance upsert functions from
their dedicated modules. Both modules implement the critical
**MANUAL_CSV provenance rule**: rows with ``data_source = 'MANUAL_CSV'``
are never overwritten by API-sourced data.

Usage::

    from app.crud.attendance import (
        upsert_daily_batch,
        upsert_daily_record,
        sync_monthly_batch,
        upsert_monthly_record,
    )
"""
from app.crud.crud_daily import (
    upsert_daily_batch,
    upsert_daily_record,
)
from app.crud.crud_monthly import (
    sync_monthly_batch,
    upsert_monthly_record,
)

__all__ = [
    "upsert_daily_batch",
    "upsert_daily_record",
    "sync_monthly_batch",
    "upsert_monthly_record",
]
