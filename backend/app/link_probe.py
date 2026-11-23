"""v2.8 (experimental): independent link-state measurement for link-aware detection.

A background thread sends a small UDP probe every PROBE_INTERVAL seconds to an echo
responder on the far side of each monitored link (in a deployment: the satellite
terminal or 5G router at the remote site; in the testbed: a responder inside the
device namespace, reached through the emulated link). A link is declared DOWN when no
reply has arrived for PROBE_DOWN_AFTER seconds and UP again on the first reply. Every
outage is kept as an interval [t_down, t_up], where t_down is the send time of the
first unanswered probe. Nothing the devices themselves report is trusted.

  LINK_PROBE_TARGETS = "sat=10.9.0.2:9998,g5=10.8.0.2:9998"
  DEVICE_LINK_DEFAULT = "sat"          (link that devices use unless mapped)
"""
import os, socket, threading, time

PROBE_INTERVAL = float(os.getenv("PROBE_INTERVAL", "0.5"))
PROBE_DOWN_AFTER = float(os.getenv("PROBE_DOWN_AFTER", "1.5"))


class LinkProbe:
    def __init__(self) -> None:
        self.targets = {}
        for item in filter(None, os.getenv("LINK_PROBE_TARGETS", "").split(",")):
            name, addr = item.split("="); host, port = addr.split(":")
            self.targets[name] = (host, int(port))
        self.default = os.getenv("DEVICE_LINK_DEFAULT", next(iter(self.targets), ""))
        self.state = {n: {"up": True, "last_reply": time.time(), "first_unanswered": None} for n in self.targets}
        self.outages: dict[str, list[list[float | None]]] = {n: [] for n in self.targets}
        self.lock = threading.Lock()
        self.log = open(os.getenv("LINK_PROBE_LOG", "link_probe.csv"), "a")
        self.started = False

    def start(self) -> None:
        if self.started or not self.targets:
            return
        self.started = True
        for name, addr in self.targets.items():
            threading.Thread(target=self._run, args=(name, addr), daemon=True).start()

    def _run(self, name, addr) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(0.05)
        sent: dict[int, float] = {}; k = 0; next_t = time.time()
        while True:
            now = time.time()
            if now >= next_t:
                k += 1; sent[k] = now; next_t += PROBE_INTERVAL
                try: s.sendto(str(k).encode(), addr)
                except OSError: pass
            try:
                data, _ = s.recvfrom(64); r = time.time(); kk = int(data)
                with self.lock:
                    st = self.state[name]; st["last_reply"] = r
                    if not st["up"]:
                        st["up"] = True; self.outages[name][-1][1] = r
                        self.log.write(f"{name},up,{r:.3f}\n"); self.log.flush()
                    st["first_unanswered"] = None
                for old in [x for x in sent if x <= kk]: sent.pop(old)
            except (socket.timeout, ValueError, OSError):
                pass
            with self.lock:
                st = self.state[name]
                pend = [t for t in sent.values() if t > st["last_reply"]]
                if pend and st["first_unanswered"] is None: st["first_unanswered"] = min(pend)
                if st["up"] and time.time() - st["last_reply"] > PROBE_DOWN_AFTER:
                    st["up"] = False; t0 = st["first_unanswered"] or st["last_reply"]
                    self.outages[name].append([t0, None])
                    self.log.write(f"{name},down,{t0:.3f}\n"); self.log.flush()
            for old in [x for x, t in sent.items() if time.time() - t > 30]: sent.pop(old)

    def link_of(self, device_id: str) -> str:
        return self.default

    def outage_at(self, device_id: str, t: float, margin: float = 0.0):
        """The outage interval of the device's link that contains time t, or None."""
        name = self.link_of(device_id)
        with self.lock:
            for iv in reversed(self.outages.get(name, [])):
                end = iv[1] if iv[1] is not None else time.time()
                if iv[0] - margin <= t <= end:
                    return (iv[0], iv[1])
        return None

    def recovered_within(self, device_id: str, now: float, window: float) -> bool:
        name = self.link_of(device_id)
        with self.lock:
            return any(iv[1] is not None and 0 <= now - iv[1] <= window for iv in self.outages.get(name, []))


probe = LinkProbe()
