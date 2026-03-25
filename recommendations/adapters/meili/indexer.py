from .client import client


def push_to_meili(docs, index_name: str, primary_key: str = "skuid"):
    """
    Push documents to meili index
    """
    if not docs:
        print(" No documents to index.")
        return

    index = client.index(index_name)

    # Create index if not exists
    try:
        index.get_stats()
    except Exception:
        client.create_index(index_name, {"primaryKey": primary_key})
        print(f" Created index: {index_name}")

    # Add documents
    task = index.add_documents(docs)

    print(f"🚀 Indexing started... Task UID: {task.task_uid}")

    # Optional: wait for completion
    client.wait_for_task(task.task_uid)

    print(" Documents successfully indexed in meili")