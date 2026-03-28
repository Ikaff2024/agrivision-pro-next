"""
AgriVision Pro — Smoke Tests post-déploiement
Vérifie que l'API de production répond correctement sur tous les endpoints critiques.

Usage :
  python smoke_tests.py                          # teste localhost:8000
  python smoke_tests.py https://ton-api.railway.app
"""
import sys
import json
import time
import urllib.request
import urllib.error

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = []


def req(method, path, body=None, token=None, expected=200):
    url = BASE_URL + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(r, timeout=10) as res:
            status = res.status
            resp   = json.loads(res.read().decode())
            ok = (status == expected)
            icon = PASS if ok else FAIL
            print(f"  {icon}  {method} {path} → {status}")
            results.append(ok)
            return resp if ok else None
    except urllib.error.HTTPError as e:
        status = e.code
        ok = (status == expected)
        icon = PASS if ok else FAIL
        print(f"  {icon}  {method} {path} → {status}")
        results.append(ok)
        return None
    except Exception as e:
        print(f"  {FAIL}  {method} {path} → ERREUR: {e}")
        results.append(False)
        return None


print(f"\n{'='*55}")
print(f"  AgriVision Pro — Smoke Tests")
print(f"  Target : {BASE_URL}")
print(f"{'='*55}\n")

# ── 1. Health check ───────────────────────────────────────────────────────────
print("[ Health ]")
health = req("GET", "/health")
assert health and health.get("status") == "ok", "Health check échoué"

# ── 2. Docs disponibles ───────────────────────────────────────────────────────
print("\n[ Documentation ]")
try:
    urllib.request.urlopen(BASE_URL + "/docs", timeout=5)
    print(f"  {PASS}  GET /docs → 200")
    results.append(True)
except:
    print(f"  {FAIL}  GET /docs → inaccessible")
    results.append(False)

# ── 3. Inscription ────────────────────────────────────────────────────────────
print("\n[ Authentification ]")
ts = int(time.time())
test_email = f"smoke_{ts}@test.ci"

register_res = req("POST", "/auth/register", {
    "email": test_email,
    "password": "smoketest123",
    "role": "admin",
    "cooperative_name": f"Smoke Coop {ts}",
    "country": "Côte d'Ivoire",
}, expected=201)

# ── 4. Login ──────────────────────────────────────────────────────────────────
login_res = req("POST", "/auth/login", {
    "email": test_email,
    "password": "smoketest123",
})
access_token  = login_res.get("access_token")  if login_res else None
refresh_token = login_res.get("refresh_token") if login_res else None

# ── 5. Refresh token ──────────────────────────────────────────────────────────
if refresh_token:
    refresh_res = req("POST", "/auth/refresh", {"refresh_token": refresh_token})
    new_token = refresh_res.get("access_token") if refresh_res else None
    if new_token:
        access_token = new_token  # utiliser le token rafraîchi

# ── 6. Mauvais login → 401 ────────────────────────────────────────────────────
req("POST", "/auth/login", {"email": test_email, "password": "wrong"}, expected=401)

# ── 7. Endpoints protégés sans token → 401 ───────────────────────────────────
print("\n[ Protection des routes ]")
req("GET", "/plantations", expected=401)
req("GET", "/diagnostics", expected=401)
req("GET", "/map/stats",   expected=401)

# ── 8. Endpoints protégés avec token ─────────────────────────────────────────
if access_token:
    print("\n[ Routes authentifiées ]")
    req("GET", "/plantations", token=access_token)
    req("GET", "/diagnostics", token=access_token)
    req("GET", "/map/stats",   token=access_token)
    req("GET", "/map/plantations", token=access_token)

    # Créer une plantation
    print("\n[ Métier ]")
    p = req("POST", "/plantations", {
        "name": f"Smoke Plantation {ts}",
        "owner_name": "Smoke Test",
        "country": "Côte d'Ivoire",
        "region": "Soubré",
        "latitude": 5.78,
        "longitude": -6.59,
        "hectares": 3.0,
    }, token=access_token)

    # Diagnostic sur la plantation créée
    if p and p.get("id"):
        pid = p["id"]
        req("POST", f"/cacao/diagnostic?plantation_id={pid}", {
            "country": "Côte d'Ivoire",
            "region": "Soubré",
            "rainfall_mm_month": 120.0,
            "humidity_pct": 70.0,
            "avg_temp_c": 27.0,
            "plantation_age_years": 12.0,
            "shade_tree_density_pct": 35.0,
        }, token=access_token)

        req("GET", f"/plantations/{pid}/history", token=access_token)
        req("GET", f"/plantations/{pid}/satellite", token=access_token)

# ── Résultat final ────────────────────────────────────────────────────────────
total  = len(results)
passed = sum(results)
failed = total - passed

print(f"\n{'='*55}")
if failed == 0:
    print(f"  {PASS}  TOUS LES TESTS PASSÉS ({passed}/{total})")
    print(f"  API production-ready ✓")
else:
    print(f"  {FAIL}  {failed} TEST(S) ÉCHOUÉ(S) sur {total}")
    print(f"  Vérifiez les logs avant de déployer.")
print(f"{'='*55}\n")

sys.exit(0 if failed == 0 else 1)
