import time
import statistics
import main

def probe():
    times = []
    for _ in range(5):
        start = time.time()
        res = main.build_jarvis()
        
        # Shutdown if possible
        if isinstance(res, tuple):
            for x in res:
                if hasattr(x, "shutdown"):
                    x.shutdown()
        elif hasattr(res, "shutdown"):
            res.shutdown()
            
        times.append(time.time() - start)

    print(f"Median: {statistics.median(times):.4f}s")
    print(f"Max: {max(times):.4f}s")
    print(f"Runs: {times}")

if __name__ == "__main__":
    probe()
