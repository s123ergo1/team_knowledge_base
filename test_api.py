# -*- coding: utf-8 -*-
import json
import logging
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"


# ── Buffered logger: collects lines, flushes on demand ────────────────────

class _BufferHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(self.format(record))

    def flush_and_clear(self):
        lines = self.records[:]
        self.records.clear()
        return lines


_buf = _BufferHandler()
_buf.setFormatter(logging.Formatter("  %(asctime)s [%(levelname)-5s] %(message)s", "%H:%M:%S"))

logger = logging.getLogger("api_test")
logger.setLevel(logging.DEBUG)
logger.addHandler(_buf)
logger.propagate = False


def _flush_log():
    lines = _buf.flush_and_clear()
    if lines:
        print("  --- LOG ---")
        for line in lines:
            print(line)


# ── HTTP helper ────────────────────────────────────────────────────────────

def call(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req) as r:
            resp_body = json.loads(r.read())
            return r.status, resp_body, (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), (time.time() - t0) * 1000


# ── Output helper ──────────────────────────────────────────────────────────

def _print_result(title, ok, status, detail, ms):
    badge = "PASS" if ok else "FAIL"
    print(f"\n[{badge}]  {title}")
    print(f"        status={status}  {detail}  ({ms:.0f}ms)")
    _flush_log()


def _sep(char="-", width=58):
    print(char * width)


# ── Individual tests ───────────────────────────────────────────────────────

def test_create_query():
    title = "POST /api/queries  -  create query"
    body = {"user_name": "Тест Пользователь", "question": "Как оформить отпуск?"}
    logger.debug("-> POST /api/queries  body=%s", json.dumps(body, ensure_ascii=False))
    status, resp, ms = call("POST", "/api/queries", body)
    logger.debug("<- %d | %.0fms | id=%s status=%s", status, ms, resp.get("id"), resp.get("status"))
    ok = status == 201 and resp.get("status") == "new" and "id" in resp
    _print_result(title, ok, status, f"id={resp.get('id')}", ms)
    return ok, resp.get("id")


def test_create_query_empty():
    title = "POST /api/queries  -  empty fields rejected (422)"
    body = {"user_name": "", "question": ""}
    logger.debug("-> POST /api/queries  body=%s", json.dumps(body))
    status, resp, ms = call("POST", "/api/queries", body)
    logger.debug("<- %d | %.0fms | validation error caught", status, ms)
    ok = status == 422
    _print_result(title, ok, status, "expected 422 Unprocessable Entity", ms)
    return ok, None


def test_get_queries():
    title = "GET  /api/queries  -  list all"
    logger.debug("-> GET /api/queries")
    status, resp, ms = call("GET", "/api/queries")
    count = len(resp) if isinstance(resp, list) else "?"
    logger.debug("<- %d | %.0fms | %s records", status, ms, count)
    ok = status == 200 and isinstance(resp, list) and len(resp) > 0
    _print_result(title, ok, status, f"{count} records", ms)
    return ok


def test_get_queries_pagination():
    title = "GET  /api/queries?skip=0&limit=1  -  pagination"
    logger.debug("-> GET /api/queries?skip=0&limit=1")
    status, resp, ms = call("GET", "/api/queries?skip=0&limit=1")
    count = len(resp) if isinstance(resp, list) else "?"
    logger.debug("<- %d | %.0fms | %s records (max 1)", status, ms, count)
    ok = status == 200 and isinstance(resp, list) and len(resp) <= 1
    _print_result(title, ok, status, f"{count} records (max 1)", ms)
    return ok


def test_process_query(query_id):
    title = f"POST /api/queries/{query_id}/process  -  process"
    logger.debug("-> POST /api/queries/%d/process", query_id)
    status, resp, ms = call("POST", f"/api/queries/{query_id}/process")
    logger.debug("<- %d | %.0fms | new_status=%s  confidence=%.2f",
                 status, ms,
                 resp.get("new_status"),
                 resp.get("llm_response", {}).get("confidence_score", 0))
    ok = status == 200 and resp.get("new_status") == "processed"
    _print_result(title, ok, status, f"new_status={resp.get('new_status')}", ms)
    return ok


def test_process_not_found():
    title = "POST /api/queries/99999/process  -  404 not found"
    logger.debug("-> POST /api/queries/99999/process")
    status, resp, ms = call("POST", "/api/queries/99999/process")
    logger.debug("<- %d | %.0fms", status, ms)
    ok = status == 404
    _print_result(title, ok, status, "expected 404", ms)
    return ok


# ── Run all ────────────────────────────────────────────────────────────────

def run_all():
    _sep("=")
    print("  Running all tests")
    _sep("=")

    results = []
    ok, qid = test_create_query();          results.append(ok)
    ok, _   = test_create_query_empty();    results.append(ok)
    ok      = test_get_queries();           results.append(ok)
    ok      = test_get_queries_pagination(); results.append(ok)
    if qid:
        ok  = test_process_query(qid);      results.append(ok)
    ok      = test_process_not_found();     results.append(ok)

    passed = sum(results)
    total  = len(results)
    print("")
    _sep()
    status_str = "ALL PASSED" if passed == total else f"{passed}/{total} PASSED"
    print(f"  Result: {status_str}")
    _sep()


# ── Menu ───────────────────────────────────────────────────────────────────

MENU = """
==========================================
  Team Knowledge Base API  -  CLI Tester
==========================================

  1.  POST /api/queries                   Create query
  2.  POST /api/queries (empty fields)    Validation check
  3.  GET  /api/queries                   List all queries
  4.  GET  /api/queries?limit=1           Pagination
  5.  POST /api/queries/{id}/process      Process query (enter ID)
  6.  POST /api/queries/99999/process     404 not found
  7.  Run all tests

  0.  Exit

"""


def main():
    print(MENU)
    while True:
        try:
            choice = input("  > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            sys.exit(0)

        if choice == "0":
            print("Bye.")
            sys.exit(0)

        elif choice == "1":
            test_create_query()

        elif choice == "2":
            test_create_query_empty()

        elif choice == "3":
            test_get_queries()

        elif choice == "4":
            test_get_queries_pagination()

        elif choice == "5":
            try:
                qid = int(input("  Query ID: ").strip())
            except (ValueError, EOFError):
                print("  Invalid ID.")
                continue
            test_process_query(qid)

        elif choice == "6":
            test_process_not_found()

        elif choice == "7":
            run_all()

        else:
            print("  Unknown option. Enter 0-7.")
            continue

        try:
            print("\n  Press Enter to return to menu...")
            input()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            sys.exit(0)
        print(MENU)


if __name__ == "__main__":
    main()
