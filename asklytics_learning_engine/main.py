from __future__ import annotations

import argparse
import os

try:
    # When run as a module: python -m asklytics_learning_engine.main
    from .learning.nightly_job import run_all_jobs, start_scheduler
    from .learning.embedder import build_faiss_index
    from .learning import experience_store as xp
except ImportError:
    # Fallback to allow running as a script from the package folder:
    #   cd asklytics_learning_engine && python main.py
    import os, sys
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from asklytics_learning_engine.learning.nightly_job import run_all_jobs, start_scheduler
    from asklytics_learning_engine.learning.embedder import build_faiss_index
    from asklytics_learning_engine.learning import experience_store as xp


def _reindex():
    # Rebuild from all experiences
    pairs = []
    for e in xp.get_all_experiences():
        text = f"Prompt: {e.user_prompt}\nSQL: {e.validated_sql or e.generated_sql or ''}\nContext: {e.schema_context or ''}"
        pairs.append((e.id, text))
    build_faiss_index(pairs)
    print("Rebuilt FAISS index from", len(pairs), "experiences")


def main():
    p = argparse.ArgumentParser(description="AskLytics Learning Engine entrypoint")
    p.add_argument("--nightly", action="store_true", help="Run and schedule nightly jobs")
    p.add_argument("--reindex", action="store_true", help="Rebuild FAISS index now")
    args = p.parse_args()

    if args.reindex:
        _reindex()
        return
    if args.nightly:
        # Run once and keep scheduler alive
        run_all_jobs()
        start_scheduler()
        try:
            import time
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return
    p.print_help()


if __name__ == "__main__":
    main()
