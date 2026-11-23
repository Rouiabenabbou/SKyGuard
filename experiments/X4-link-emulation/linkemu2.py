"""User-space packet-level link emulator (used because the test kernel has no netem).

Creates a network namespace and a pair of TUN interfaces: <name>a in the root
namespace and <name>b inside the namespace. Every IP packet that crosses the link is
read by this program and written to the other side after a one-way delay
(base +/- jitter, normally distributed, never re-ordered) or dropped with the given
loss probability. v2 adds Gilbert-Elliott burst loss ({"ge": {"p_gb": .., "p_bg": ..}},
loss only in the Bad state, independent state per direction) and a bandwidth limit
({"rate_kbps": R, "qmax_ms": Q}: serialization delay len*8/R with a drop-tail queue of
at most Q ms), applied before the propagation delay. Writing {"down": true} into the control file cuts the link
(100 % loss) until it is set back to false. The control file is re-read every 50 ms,
so delay, jitter, loss and down can be changed while traffic is running.

  python linkemu.py --ns devns --name sat --host-ip 10.9.0.1 --dev-ip 10.9.0.2 --ctl sat.json
"""
import argparse, fcntl, heapq, json, os, random, struct, subprocess, threading, time

TUNSETIFF, IFF_TUN, IFF_NO_PI = 0x400454ca, 0x0001, 0x1000


def tun(name):
    fd = os.open("/dev/net/tun", os.O_RDWR)
    fcntl.ioctl(fd, TUNSETIFF, struct.pack("16sH", name.encode(), IFF_TUN | IFF_NO_PI))
    return fd


def sh(*a):
    subprocess.run(a, check=True)


class Link:
    def __init__(self, ctl):
        self.ctl, self.mtime = ctl, 0
        self.cfg = {"delay_ms": 0, "jitter_ms": 0, "loss": 0.0, "down": False, "ge": None, "rate_kbps": 0, "qmax_ms": 2000}
        self.stats = {"in": 0, "dropped": 0}
        self.reload()

    def reload(self):
        try:
            m = os.path.getmtime(self.ctl)
            if m != self.mtime:
                self.mtime = m
                self.cfg.update(json.load(open(self.ctl)))
        except (OSError, ValueError):
            pass


def forward(src, dst, link, name):
    q, lock, last = [], threading.Condition(), [0.0]
    bad, free = [False], [0.0]  # Gilbert-Elliott state, time the bottleneck is free

    def sender():
        while True:
            with lock:
                while not q or q[0][0] > time.monotonic():
                    lock.wait(None if not q else max(0, q[0][0] - time.monotonic()))
                _, _, pkt = heapq.heappop(q)
            os.write(dst, pkt)

    threading.Thread(target=sender, daemon=True).start()
    n = 0
    while True:
        pkt = os.read(src, 65535)
        c = link.cfg
        link.stats["in"] += 1
        ge = c.get("ge")
        if ge:
            bad[0] = (random.random() >= ge["p_bg"]) if bad[0] else (random.random() < ge["p_gb"])
        if c["down"] or random.random() < c["loss"] or (ge and bad[0]):
            link.stats["dropped"] += 1
            continue
        now = time.monotonic()
        if c.get("rate_kbps"):
            start = max(now, free[0])
            if start - now > c.get("qmax_ms", 2000) / 1000:  # queue full: drop-tail
                link.stats["dropped"] += 1
                continue
            free[0] = start + len(pkt) * 8 / (c["rate_kbps"] * 1000)
            now = free[0]
        d = max(0.0, random.gauss(c["delay_ms"], c["jitter_ms"])) / 1000
        t = max(now + d, last[0])  # no re-ordering
        last[0] = t; n += 1
        with lock:
            heapq.heappush(q, (t, n, pkt)); lock.notify()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns", required=True); ap.add_argument("--name", required=True)
    ap.add_argument("--host-ip", required=True); ap.add_argument("--dev-ip", required=True)
    ap.add_argument("--ctl", required=True)
    a = ap.parse_args()
    if not os.path.exists(f"/var/run/netns/{a.ns}"):
        sh("ip", "netns", "add", a.ns)
        sh("ip", "netns", "exec", a.ns, "ip", "link", "set", "lo", "up")
    ta = tun(a.name + "a")
    root = os.open("/proc/self/ns/net", os.O_RDONLY)
    nsfd = os.open(f"/var/run/netns/{a.ns}", os.O_RDONLY)
    os.setns(nsfd, os.CLONE_NEWNET); tb = tun(a.name + "b"); os.setns(root, os.CLONE_NEWNET)
    sh("ip", "addr", "add", f"{a.host_ip}/32", "peer", a.dev_ip, "dev", a.name + "a"); sh("ip", "link", "set", a.name + "a", "up")
    sh("ip", "netns", "exec", a.ns, "ip", "addr", "add", f"{a.dev_ip}/32", "peer", a.host_ip, "dev", a.name + "b")
    sh("ip", "netns", "exec", a.ns, "ip", "link", "set", a.name + "b", "up")
    link = Link(a.ctl)
    threading.Thread(target=forward, args=(ta, tb, link, "down"), daemon=True).start()
    threading.Thread(target=forward, args=(tb, ta, link, "up"), daemon=True).start()
    print(f"link {a.name}: {a.host_ip} (root) <-> {a.dev_ip} (ns {a.ns}) ready", flush=True)
    while True:
        time.sleep(0.05); link.reload()


if __name__ == "__main__":
    main()
