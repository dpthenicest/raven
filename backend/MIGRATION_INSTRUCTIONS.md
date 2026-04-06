# Database Migration Instructions

## Adding the "-" (Unknown) Tariff Band

The application now supports a "-" tariff band value for feeders where the band couldn't be detected during OCR parsing.

### Step 1: Run the Migration

From the `backend` directory, run:

```bash
# Activate your virtual environment first
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

# Run the migration
alembic upgrade head
```

### Step 2: Verify the Migration

You should see output like:
```
INFO  [alembic.runtime.migration] Running upgrade 02314e4324a0 -> b465733dae8f, add_unknown_tariff_band
```

### Step 3: Verify in Database

Connect to your PostgreSQL database and check:

```sql
-- Check the enum values
SELECT unnest(enum_range(NULL::tariffband));
```

You should see:
```
A
B
C
D
E
-
```

### Troubleshooting

**If you get "command not found: alembic":**
```bash
# Make sure you're in the virtual environment
which python  # Should show .venv/bin/python

# Try with python -m
python -m alembic upgrade head
```

**If migration fails with "can't locate revision":**
```bash
# Check current database version
alembic current

# Check available migrations
alembic history
```

**If you need to rollback:**
```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade 02314e4324a0
```

### What This Migration Does

The migration adds a new value "-" to the `tariffband` PostgreSQL enum type. This allows feeders with undetected bands to be stored in the database with a placeholder value that can be updated later via the admin API.

**Before migration:**
- Feeders with missing bands would fail to save
- Error: `invalid input value for enum tariffband: "UNKNOWN"`

**After migration:**
- Feeders with missing bands are saved with `tariff_band = "-"`
- Can be updated later using `PUT /admin/feeders/{feeder_id}`

### Next Steps After Migration

1. **Parse NERC PDFs** - The parser will now save feeders with "-" for missing bands
2. **Review fallback feeders** - Check `fallback_count` in parse response
3. **Update unknown bands** - Use admin API to set correct bands:
   ```bash
   PUT /admin/feeders/{feeder_id}
   {
     "tariff_band": "C"
   }
   ```

### Migration File Location

`backend/alembic/versions/b465733dae8f_add_unknown_tariff_band.py`
