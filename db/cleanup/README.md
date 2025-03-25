# Database Cleanup Scripts

This directory contains scripts to check for videos that exist in the Chroma vector database but not in the SQLite database (`video_processing.db`) and remove those entries from Chroma.

## Purpose

The video processing system uses two databases:
1. A SQLite database (`video_processing.db`) that stores metadata about processed videos
2. A Chroma vector database (`chroma_db`) that stores vector embeddings for semantic search

Both databases use the same identifier (MD5 hash of the file path) to identify videos. Over time, these databases might get out of sync if:
- Videos are deleted from the SQLite database but not from Chroma
- The SQLite database is restored from a backup but Chroma is not
- Processing errors occur that add a video to one database but not the other

These scripts help maintain database integrity by removing entries from the Chroma database that don't exist in the SQLite database.

## Scripts

### 1. test_db_cleanup.py

This script tests the database connections and identifies potential orphaned entries without deleting them.

```bash
# Run the test script
python -m db.cleanup.test_db_cleanup
```

### 2. db_cleanup.py

This script identifies and removes entries from the Chroma database that don't exist in the SQL database.

```bash
# Run with default database paths (dry run mode)
python -m db.cleanup.db_cleanup --dry-run

# Run with default database paths (actual deletion)
python -m db.cleanup.db_cleanup

# Specify custom database paths
python -m db.cleanup.db_cleanup --db-path /path/to/video_processing.db --chroma-path /path/to/chroma_db
```

### Command-line Arguments

- `--dry-run`: Only print what would be deleted without actually deleting anything
- `--db-path`: Path to the SQLite database file (default: `db/data/video_processing.db`)
- `--chroma-path`: Path to the Chroma database directory (default: `db/data/chroma_db`)

## How It Works

1. The script connects to both databases
2. It retrieves all video IDs from the SQLite database
3. It retrieves all document IDs from the Chroma database
4. It identifies Chroma entries that don't have a corresponding entry in the SQLite database
5. It deletes those orphaned entries from Chroma (or just lists them in dry-run mode)

## Recommended Usage

It's recommended to:

1. First run the test script to check if there are any orphaned entries:
   ```bash
   python -m db.cleanup.test_db_cleanup
   ```

2. If orphaned entries are found, run the cleanup script in dry-run mode to see what would be deleted:
   ```bash
   python -m db.cleanup.db_cleanup --dry-run
   ```

3. If everything looks correct, run the cleanup script to actually delete the orphaned entries:
   ```bash
   python -m db.cleanup.db_cleanup
   ```

## Notes

- The script processes deletions in batches of 100 documents to avoid potential issues with large deletions
- Both description documents and their associated transcript documents (if any) will be deleted 