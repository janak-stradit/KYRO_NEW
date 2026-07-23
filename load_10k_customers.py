#!/usr/bin/env python3
"""
Load 10,000 customers into the database by running the pipeline.
This generates synthetic customer data and loads it into raw_data schema,
then syncs it to the app schema.
"""

import os
import sys
import subprocess

# Set environment variable for 10k customers
os.environ['NUM_CUSTOMERS'] = '10000'
os.environ['PIPELINE_BATCH_SIZE'] = '500'

print("=" * 70)
print("🚀 LOADING 10,000 CUSTOMERS INTO DATABASE")
print("=" * 70)
print(f"   Total customers: 10,000")
print(f"   Batch size: 500")
print(f"   Expected batches: 20")
print("=" * 70)
print()

# Run the pipeline
print("📊 Running data generation pipeline...")
print()

# Change to KYRO_NEW directory
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Run the pipeline
try:
    result = subprocess.run(
        [sys.executable, "pipeline/run_pipeline.py"],
        env={**os.environ, 'NUM_CUSTOMERS': '10000', 'PIPELINE_BATCH_SIZE': '500'},
        check=True,
        capture_output=False
    )
    
    print()
    print("=" * 70)
    print("✅ PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 70)
    print()
    print("🔄 Now syncing raw_data → app schema...")
    print()
    
    # Run sync script
    sync_result = subprocess.run(
        [sys.executable, "sync_to_app.py"],
        check=True,
        capture_output=False
    )
    
    print()
    print("=" * 70)
    print("✅ ALL DONE! 10,000 customers loaded and synced.")
    print("=" * 70)
    print()
    print("🔍 Verify with:")
    print("   ./show_customer_count.sh")
    print("   or:")
    print("   python check_customer_count.py")
    print()
    
except subprocess.CalledProcessError as e:
    print(f"\n❌ Error running pipeline: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    sys.exit(1)
