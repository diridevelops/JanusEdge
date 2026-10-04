# Bug Fix: Portable Backup Tag Categories

**Date:** 2026-10-04

## Bug

Portable backups exported tags but omitted their category definitions. Restoring a tag preserved the source `category_id`, which referred to an ID in another database and could not resolve to the restored category.

## Root Cause

`PortableBackupService._build_export_payload` included user tags but did not include documents from `tag_categories`. `_restore_tags` replaced each tag's own ID and user ID but left `category_id` unchanged.

## Fix

Export tag category documents with the backup. Restore categories by system key or name, map their source IDs to destination IDs, and apply those IDs to restored tags. Legacy archives without category definitions remain importable; newly restored tags with unresolved category IDs use the destination General category. Reused tags keep their destination category when the archive contains no category mapping.

## Verification

- `python -m py_compile app/auth/backup_service.py` passed.
- Focused backup tests: 2 passed, covering category export/remapping/idempotent restore and legacy 1.0 fallback.
- Full backend suite: 497 passed, with 8 `mongomock` `datetime.utcnow()` deprecation warnings.
- Full frontend suite: 150 passed across 23 files.
- `git diff --check` passed.
