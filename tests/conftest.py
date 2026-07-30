

def pytest_unconfigure(config):
    import threading, sys
    print('\n--- ALIVE THREADS ---')
    for t in threading.enumerate():
        print(f'Thread: {t.name}, daemon: {t.daemon}, alive: {t.is_alive()}')
    sys.stdout.flush()
