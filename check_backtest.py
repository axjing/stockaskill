import os
base = r'D:\An\CODE\akproj\.opencode\skills\stockaskill'
scripts = os.path.join(base, 'scripts')

# Clean temp file
for f in ['check_remaining.py']:
    p = os.path.join(base, f)
    if os.path.exists(p):
        os.remove(p)

# Check for backtest_enhanced.py (unexpected file)
ep = os.path.join(scripts, 'backtest_enhanced.py')
print('backtest_enhanced.py exists:', os.path.exists(ep))

# Check for any other unexpected files
print()
print('=== File inventory ===')
for root, dirs, files in os.walk(scripts):
    for fn in files:
        if fn.endswith('.py'):
            fp = os.path.join(root, fn)
            rel = fp.replace(base+'\\\\', '').replace(base+'\\', '')
            size = os.path.getsize(fp)
            print('  ' + rel + ' (' + str(size) + ' bytes)')
