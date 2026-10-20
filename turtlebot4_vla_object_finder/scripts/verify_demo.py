#!/usr/bin/env python3
"""Exercise the actual HTTP → ROS action → navigation lifecycle."""
import argparse
import json
import threading
import time
import urllib.error
import urllib.request


def http(url, path, body=None):
    request = urllib.request.Request(url + path, None if body is None else json.dumps(body).encode(),
                                     {'Content-Type': 'application/json'})
    return urllib.request.urlopen(request, timeout=310)


def run(url, prompt, navigating=None, motion_state='navigating'):
    with http(url, '/infer', {'prompt': prompt}) as response:
        events = []
        for line in response:
            if not line.strip():
                continue
            event = json.loads(line)
            events.append(event)
            if navigating is not None and event.get('status') == motion_state:
                navigating.set()
    terminal = [e for e in events if e['type'] in ('done', 'error')]
    assert len(terminal) == 1, events
    return terminal[0], events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--mode', choices=['mock', 'simulation'], default='mock')
    parser.add_argument('--expect-search', action='store_true',
                        help='Require search motion and multiple camera checks before success.')
    parser.add_argument('--prompt', help='Visible target; defaults to person in simulation, red chair in mock.')
    args = parser.parse_args()
    args.prompt = args.prompt or ('go to the standing person' if args.mode == 'simulation' else 'go to the red chair')
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            with http(args.url, '/status') as response:
                status = json.load(response)
            if status['ready'] and not status.get('busy') and status.get('stationary'):
                break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Application did not become ready.')
    print('Readiness:', json.dumps(status), flush=True)
    with http(args.url, '/video_feed') as response:
        assert b'Content-Type: image/jpeg' in response.read(64)
    result, events = run(args.url, args.prompt)
    assert result.get('success') is True, result
    assert any(e.get('status') == 'thinking' for e in events), events
    assert any(e.get('status') == 'navigating' for e in events), events
    if args.expect_search:
        assert any(e.get('status') == 'searching_navigation' for e in events), events
        assert sum(e.get('status') == 'thinking' for e in events) >= 2, events
    print('Pipeline result:', json.dumps(result), flush=True)
    if args.mode == 'mock':
        result, events = run(args.url, 'go to the hidden chair')
        assert result.get('success') is True, result
        assert any(e.get('status') == 'searching_navigation' for e in events), events
        assert sum(e.get('status') == 'thinking' for e in events) >= 2, events
        print('Previously unseen target found after a turn.', flush=True)
        result, events = run(args.url, 'go to the missing object')
        assert any('Viewpoint 2/' in e.get('text', '') for e in events), events
        assert not result.get('success'), result
        assert 'not found' in result['message'].lower(), result
        results = []
        navigating = threading.Event()
        thread = threading.Thread(target=lambda: results.append(run(args.url, args.prompt, navigating)))
        thread.start()
        try:
            for _ in range(100):
                with http(args.url, '/status') as response:
                    if json.load(response).get('busy'):
                        break
                time.sleep(.05)
            else:
                raise AssertionError('Cancellation test never observed an active goal.')
            try:
                http(args.url, '/infer', {'prompt': 'home'})
                raise AssertionError('Concurrent goal unexpectedly accepted.')
            except urllib.error.HTTPError as exc:
                assert exc.code == 409, exc.code
            assert navigating.wait(30), 'No live Nav2 feedback before cancellation'
            with http(args.url, '/cancel', {}) as response:
                assert json.load(response)['cancellation_requested']
        finally:
            thread.join(timeout=150)
        assert results and results[0][0].get('action_status') == 5, results
        search_results = []
        searching = threading.Event()
        thread = threading.Thread(target=lambda: search_results.append(
            run(args.url, 'go to the missing object', searching, 'searching_navigation')))
        thread.start()
        assert searching.wait(30), 'Search motion never started'
        with http(args.url, '/cancel', {}) as response:
            assert json.load(response)['cancellation_requested']
        thread.join(timeout=30)
        assert search_results and search_results[0][0].get('action_status') == 5, search_results
        print('Bounded map search, busy rejection, approach cancellation, and search cancellation passed.', flush=True)
    print('Verification passed. Mode:', args.mode)


if __name__ == '__main__':
    main()
