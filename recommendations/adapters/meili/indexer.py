from .client import client
import pandas as pd
import numpy as np


def push_to_meili(docs, index_name: str, primary_key: str = None):
    if not docs:
        print("❌ No documents to index.")
        return

    # ---------------------------
    # Ensure index exists
    # ---------------------------
    try:
        index = client.get_index(index_name)

    except Exception:
        print(f"🆕 Creating index: {index_name}")
        if primary_key:
            client.create_index(index_name, {"primaryKey": primary_key})
        else:
            client.create_index(index_name)

    index = client.index(index_name)

    # ---------------------------
    # Clean documents
    # ---------------------------
    clean_docs = []
    for d in docs:
        clean_doc = {}
        for k, v in d.items():
            if isinstance(v, float) and pd.isna(v):
                clean_doc[k] = None
            elif isinstance(v, (np.float32, np.float64)):
                clean_doc[k] = float(v)
            else:
                clean_doc[k] = v
        clean_docs.append(clean_doc)

    # ---------------------------
    # Push
    # ---------------------------
    task = index.add_documents(clean_docs)
    print(f"🚀 Indexing started... Task UID: {task.task_uid}")

    result = client.wait_for_task(task.task_uid)

    if result.status == "succeeded":
        print(f"✅ Indexed {len(clean_docs)} documents into '{index_name}'")
    else:
        print("❌ Indexing failed!")
        print(result.error)