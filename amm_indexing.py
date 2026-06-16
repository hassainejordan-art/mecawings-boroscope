import logging
import threading

logger = logging.getLogger(__name__)

_index_lock = threading.Lock()
_index_pending = set()


def schedule_amm_indexing(base_dir, doc_id):
    """Run PDF text extraction for one document in a background thread."""
    if not doc_id:
        return

    with _index_lock:
        if doc_id in _index_pending:
            return
        _index_pending.add(doc_id)

    def worker():
        try:
            from amm_storage import extract_and_index_amm_document

            extract_and_index_amm_document(base_dir, doc_id)
        except Exception:
            logger.exception("Background AMM indexing failed for document %s", doc_id)
            try:
                from amm_storage import mark_amm_indexing_failed

                mark_amm_indexing_failed(base_dir, doc_id)
            except Exception:
                logger.exception(
                    "Failed to mark AMM document %s as indexing_failed", doc_id
                )
        finally:
            with _index_lock:
                _index_pending.discard(doc_id)

    thread = threading.Thread(
        target=worker,
        daemon=True,
        name=f"amm-index-{doc_id}",
    )
    thread.start()


def schedule_pending_amm_indexing(base_dir):
    """Queue background indexing for documents awaiting extraction."""
    from amm_storage import list_unindexed_amm_document_ids

    for doc_id in list_unindexed_amm_document_ids(base_dir):
        schedule_amm_indexing(base_dir, doc_id)
