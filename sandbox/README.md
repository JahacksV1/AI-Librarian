# Sandbox (test data)

Synthetic, **messy** folder tree for exercising `scan_folder`, plans, and file ops.  
Nothing here is real PII or production content.

To **regenerate / extend** the messy layout:

```bash
python scripts/populate_messy_sandbox.py
```

Your original samples under `Contracts/`, `Invoices/`, `Downloads/`, etc. are kept; the script adds overlapping, oddly named, and duplicate-style paths on purpose.
