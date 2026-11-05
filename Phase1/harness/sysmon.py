"""Background sampler for CPU and memory use of the Ollama processes.

GPU utilization on Apple Silicon needs `sudo powermetrics`, so it is not
sampled here; resident model memory comes from Ollama's /api/ps instead."""

import threading
import time

import psutil


class OllamaSampler:
    def __init__(self, interval=1.0):
        self.interval = interval
        self.samples = []  # (epoch time, cpu % summed over cores, rss bytes)
        self._procs = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _ollama_procs(self):
        for p in psutil.process_iter(["name"]):
            if "ollama" in (p.info["name"] or "").lower():
                yield p

    def _run(self):
        while not self._stop.is_set():
            cpu, rss = 0.0, 0
            for p in self._ollama_procs():
                try:
                    if p.pid not in self._procs:
                        self._procs[p.pid] = p
                        p.cpu_percent(None)  # first call only primes the counter
                    cpu += self._procs[p.pid].cpu_percent(None)
                    rss += p.memory_info().rss
                except psutil.Error:
                    pass
            self.samples.append((time.time(), cpu, rss))
            self._stop.wait(self.interval)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join()

    def window(self, t0, t1):
        """Mean CPU (% of one core, and fraction of all cores) and peak RSS
        over [t0, t1]."""
        inside = [s for s in self.samples if t0 <= s[0] <= t1 + self.interval]
        if not inside:
            return {"cpu_pct": None, "cpu_util": None, "rss_gb": None}
        cpu = sum(s[1] for s in inside) / len(inside)
        return {"cpu_pct": cpu,
                "cpu_util": cpu / (100 * psutil.cpu_count()),
                "rss_gb": max(s[2] for s in inside) / 2**30}
