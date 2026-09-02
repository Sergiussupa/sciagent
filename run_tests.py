import traceback

from tests import test_core


def main():
    tests = [
        test_core.test_feed,
        test_core.test_db_collection_memory,
        test_core.test_context_budget,
        test_core.test_router_multidomain,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception:
            failed += 1
            print("FAIL", fn.__name__)
            traceback.print_exc()
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
