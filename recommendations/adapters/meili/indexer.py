from .client import client
import pandas as pd
import numpy as np





def push_to_meili(docs, index_name: str, primary_key: str = None):
    """
    Push documents to a MeiliSearch index.
    """
    if not docs:
        print("❌ No documents to index.")
        return

    # ---------------------------
    # Ensure index exists
    # ---------------------------
    try:
        client.get_index(index_name)
    except Exception:
        print(f"🆕 Creating index: {index_name}")
        if primary_key:
            client.create_index(index_name, {"primaryKey": primary_key})
        else:
            client.create_index(index_name)

    index = client.index(index_name)
    index.update_filterable_attributes(["l1", "l2", "l3", "brand"])

    # ---------------------------
    # Clean documents
    # ---------------------------
    clean_docs = []
    for d in docs:
        clean_doc = {}
        for k, v in d.items():
            key = "sku" if k == "skuid" else k  # always normalize

            if isinstance(v, float) and pd.isna(v):
                clean_doc[key] = None
            elif isinstance(v, (np.float32, np.float64)):
                clean_doc[key] = float(v)
            else:
                clean_doc[key] = v
        clean_docs.append(clean_doc)

    # ---------------------------
    # Push
    # ---------------------------
    task = index.add_documents(clean_docs)
    print(f"🚀 Indexing started... Task UID: {task.task_uid}")

    result = client.wait_for_task(task.task_uid)

    if result.status == "succeeded":
        print(f"✅ Indexed {len(clean_docs)} documents into '{index_name}'")
        print(index.get_stats())
    else:
        print("❌ Indexing failed!")
        print(result.error)
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
