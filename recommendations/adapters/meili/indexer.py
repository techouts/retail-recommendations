from .client import client
import pandas as pd
import numpy as np


def push_to_meili(docs, index_name: str, primary_key: str = "sku"):
    """
    Push documents to meili index
    """
    if not docs:
        print("❌ No documents to index.")
        return

    index = client.index(index_name)

    # Create index if not exists
    try:
        index.get_stats()
    except Exception:
        client.create_index(index_name, {"primaryKey": primary_key})
        print(f" Created index: {index_name}")
        
    index.update_filterable_attributes(["l1", "l2", "l3", "brand","skuid_A"])

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
    # Add documents
    task = index.add_documents(docs)
    
    # print("Docs sample:", docs[:2])
    # print("Task:", task)

    print(f"🚀 Indexing started... Task UID: {task.task_uid}")

    result = client.wait_for_task(task.task_uid)
    # Optional: wait for completion
    client.wait_for_task(task.task_uid)
    
    # client.delete_index("ssb2_deal_of_day")
    
    task_status = client.get_task(task.task_uid)
    # print("Task status:", task_status)
    
    print(index.get_stats())
    
    # client.delete_index("ssb1_deal_of_day")

    print(" Documents successfully indexed in meili")
    

def push_to_meili_fbt(docs, index_name: str, primary_key: str = "skuid_A"):

    if not docs:
        print("No documents to index.")
        return

    try:
        client.delete_index(index_name)
        print(f"Deleted index: {index_name}")
    except:
        pass

    client.create_index(index_name, {"primaryKey": primary_key})
    index = client.index(index_name)

    task = index.update_filterable_attributes([
        "skuid_A", "l1_A", "l2_A", "l3_A", "brand_A"
    ])
    client.wait_for_task(task.task_uid)


    task = index.add_documents(docs)
    print(f"🚀 Indexing started... Task UID: {task.task_uid}")

    client.wait_for_task(task.task_uid)

    print(index.get_stats())
    print("Documents successfully indexed in meili")