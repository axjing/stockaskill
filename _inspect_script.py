import os, re
base = r"D:\An\CODE\akproj\.opencode\skills\stockaskill"
sp = os.path.join(base, "scripts", "run.py")
with open(sp, "r", encoding="utf-8") as f:
    c = f.read()
print("run.py:", len(c), "bytes,", c.count(chr(10)), "lines")
print("Uses report_generator:", "report_generator" in c)
print("Has portfolio-enhanced:", "portfolio-enhanced" in c)
print("Has backtest-enhanced:", "backtest-enhanced" in c)
print("Has cached_only:", "cached_only" in c)
import re as re2
for m in re2.finditer(r"def (cmd_\w+)", c):
    print("  Function:", m.group(1))
for m in re2.finditer(r"sub\.add_parser\(\"([^\"]+)\"", c):
    print("  CLI command:", m.group(1))
