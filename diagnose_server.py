"""Diagnose server route registration"""
import sys
import requests
import psutil

print("\n" + "="*70)
print("ASKLYTICS SERVER DIAGNOSTICS")
print("="*70)

# Check running Python processes
print("\n[1] Running Python processes:")
for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if proc.info['name'] == 'python.exe':
            cmdline = ' '.join(proc.info['cmdline'][:2])
            if 'AskLytics' in cmdline or 'app.py' in cmdline:
                print(f"  PID {proc.info['pid']}: {cmdline}")
    except:
        pass

# Check port 5000
print("\n[2] What's using port 5000:")
for conn in psutil.net_connections():
    if conn.laddr.port == 5000:
        try:
            proc = psutil.Process(conn.pid)
            print(f"  PID {conn.pid}: {proc.name()} - Status: {conn.status}")
        except:
            print(f"  PID {conn.pid}: Unknown process")

# Test endpoints
print("\n[3] Testing endpoints:")
endpoints = [
    '/modeling',
    '/semantic/health',
    '/semantic/catalog',
    '/'
]

for endpoint in endpoints:
    try:
        url = f'http://localhost:5000{endpoint}'
        response = requests.get(url, timeout=2)
        status = "OK" if response.status_code == 200 else f"ERROR {response.status_code}"
        print(f"  {endpoint:30s} [{status}]")
    except requests.exceptions.ConnectionError:
        print(f"  {endpoint:30s} [CONNECTION REFUSED - Server not running?]")
    except Exception as e:
        print(f"  {endpoint:30s} [ERROR: {str(e)[:40]}]")

print("\n" + "="*70)
print("RECOMMENDATION:")
print("="*70)

# Check if app.py routes are registered
try:
    sys.path.insert(0, '.')
    import app
    
    modeling_route = any('modeling' in str(r.rule) for r in app.app.url_map.iter_rules())
    semantic_routes = [str(r.rule) for r in app.app.url_map.iter_rules() if 'semantic' in str(r.rule)]
    
    print(f"\n✓ Code has /modeling route: {modeling_route}")
    print(f"✓ Code has {len(semantic_routes)} semantic routes")
    
    if modeling_route:
        print("\n✅ Routes ARE in the code!")
        print("❌ But server returns 404 = OLD SERVER STILL RUNNING")
        print("\nACTION NEEDED:")
        print("  1. Kill ALL Python processes: Get-Process python | Stop-Process -Force")
        print("  2. Wait 5 seconds")
        print("  3. Start fresh: python app.py")
    else:
        print("\n❌ Routes NOT in code - file changes may have been reverted")
        
except Exception as e:
    print(f"\n⚠️  Could not import app.py: {e}")

print("\n" + "="*70 + "\n")

