#!/usr/bin/env python3
"""Read Prometheus's alert state on this host.
  ceph-alerts.py rules    every alerting rule, its for-duration and state
  ceph-alerts.py          alerts now pending or firing
  ceph-alerts.py follow   print the time and the alerts each time the set changes (Ctrl-C to stop)
"""
import json, sys, time, urllib.request

API = "http://localhost:9095/api/v1/"

def get(path):
    return json.load(urllib.request.urlopen(API + path, timeout=10))["data"]

def alerts():
    out = []
    for a in get("alerts")["alerts"]:
        out.append((a["labels"]["alertname"], a["state"], a["labels"].get("severity", ""),
                    a["labels"].get("ceph_daemon", a["labels"].get("hostname", a["labels"].get("instance", "")))))
    return sorted(set(out))

mode = sys.argv[1] if len(sys.argv) > 1 else "now"
if mode == "rules":
    groups = get("rules?type=alert")["groups"]
    rules = [(g["name"], r) for g in groups for r in g["rules"]]
    states = {}
    for _, r in rules:
        states[r["state"]] = states.get(r["state"], 0) + 1
    print(len(rules), "alert rules in", len(groups), "groups:", ", ".join("%d %s" % (n, s) for s, n in sorted(states.items())))
    for g, r in rules:
        print("  %-24s %-42s for %4ds  %s" % (g[:24], r["name"], int(r.get("duration", 0)), r["state"]))
elif mode == "follow":
    prev = None
    while True:
        try:
            cur = alerts()
        except Exception as e:
            cur = [("(Prometheus unreachable: %s)" % e, "", "", "")]
        if cur != prev:
            print(time.strftime("%H:%M:%S", time.gmtime()), "-", len(cur), "pending or firing")
            for name, state, sev, who in cur:
                print("    %-8s %-40s %-9s %s" % (state, name, sev, who))
            sys.stdout.flush()
            prev = cur
        time.sleep(5)
else:
    cur = alerts()
    print(len(cur), "pending or firing")
    for name, state, sev, who in cur:
        print("    %-8s %-40s %-9s %s" % (state, name, sev, who))