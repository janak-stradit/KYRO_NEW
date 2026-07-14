import sys
import os
import json
import logging
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.core.database import get_engine
from pipeline.run_pipeline import AMLPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reprocess_dlq():
    logger.info("Checking for records in Dead Letter Queue (raw_data.rejected_records)...")
    try:
        engine = get_engine()
        df = pd.read_sql("SELECT * FROM raw_data.rejected_records WHERE reprocessed = FALSE", engine)
        
        if df.empty:
            logger.info("No records to reprocess.")
            return

        logger.info(f"Found {len(df)} rejected records to attempt reprocessing.")
        
        dataset = {"customers": [], "accounts": [], "transactions": []}
        for _, row in df.iterrows():
            entity = row["entity_type"].lower().rstrip("s") + "s"  # normalize to 'customers', 'accounts', 'transactions'
            payload = row["raw_payload"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode payload for record ID {row['id']}")
                    continue
            if entity in dataset and isinstance(payload, dict):
                dataset[entity].append(payload)

        # Re-run pipeline on the rejected subset. The pipeline now has smart null filling and deduplication.
        pipeline = AMLPipeline()
        stats = pipeline.run(dataset=dataset)
        
        # Mark as reprocessed
        with engine.begin() as conn:
            conn.execute(text("UPDATE raw_data.rejected_records SET reprocessed = TRUE WHERE reprocessed = FALSE"))
            
        logger.info(f"Reprocessing complete. Batch Execution ID: {stats.get('execution_id')}")
        
    except Exception as exc:
        logger.error(f"Failed to reprocess DLQ: {exc}")

if __name__ == "__main__":
    reprocess_dlq()
