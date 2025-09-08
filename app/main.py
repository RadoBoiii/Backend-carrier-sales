# app/main.py
import os, re, json, csv, time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Header, Depends, Response
from pydantic import BaseModel

# ---------- Config ----------
FMCSA_BASE   = os.getenv("QCMOBILE_BASE", "https://mobile.fmcsa.dot.gov/qc/services")
FMCSA_WEBKEY = os.getenv("FMCSA_WEBKEY", "")
API_KEY      = os.getenv("API_KEY", "")
LOADS_PATH   = os.getenv("LOADS_PATH", "/app/loads.json")  # can be .json or .csv
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "6.0"))
MC_RE        = re.compile(r"^\d{4,7}$")

# ---------- Auth ----------
def require_api_key(x_api_key: str = Header(default="")):
    if not API_KEY:
        raise HTTPException(500, "Server missing API_KEY")
    if x_api_key != API_KEY:
        raise HTTPException(401, "Invalid API key")

app = FastAPI(title="Inbound Carrier Backend (file-backed)")

# ---------- Health (no auth) ----------
@app.get("/healthz")
def healthz():
    return {"ok": True, "ts": int(time.time())}

# ---------- Models ----------
class CarrierVerdict(BaseModel):
    eligible: bool
    reason: str
    mc_number: Optional[str] = None
    dot_number: Optional[str] = None
    legal_name: Optional[str] = None
    dba_name: Optional[str] = None
    out_of_service_date: Optional[str] = None

class OfferLog(BaseModel):
    call_id: str
    load_id: str
    mc_number: str
    carrier_offer: float
    round: int
    broker_offer: Optional[float] = None
    accepted: Optional[bool] = None

class CallSummary(BaseModel):
    call_id: str
    carrier_mc: Optional[str] = None
    load_id: Optional[str] = None
    final_price: Optional[float] = None
    outcome: Optional[str] = None
    sentiment: Optional[str] = None
    offer_history: Optional[List[float]] = None
    transcript_url: Optional[str] = None

# ---------- Data loading (file-backed) ----------
def _load_file_rows(path: str) -> List[Dict[str, Any]]:
    if path.lower().endswith(".json"):
        with open(path) as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            raise RuntimeError("loads.json must contain a JSON array")
    elif path.lower().endswith(".csv"):
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    else:
        raise RuntimeError("LOADS_PATH must be .json or .csv")

try:
    LOADS = _load_file_rows(LOADS_PATH)
except Exception as e:
    # Safe fallback demo data if file missing
    LOADS = [
        {
            "load_id": "L-1001",
            "origin": "Chicago, IL",
            "destination": "Dallas, TX",
            "pickup_datetime": "2025-09-08T08:00:00-05:00",
            "delivery_datetime": "2025-09-09T16:00:00-05:00",
            "equipment_type": "Dry Van",
            "loadboard_rate": 1450,
            "notes": "No pallet exchange",
            "weight": 30000,
            "commodity_type": "Paper",
            "num_of_pieces": 20,
            "miles": 976,
            "dimensions": "48x102"
        },
        {
            "load_id": "L-1002",
            "origin": "Atlanta, GA",
            "destination": "Orlando, FL",
            "pickup_datetime": "2025-09-08T07:00:00-05:00",
            "delivery_datetime": "2025-09-08T17:00:00-05:00",
            "equipment_type": "Reefer",
            "loadboard_rate": 900,
            "notes": "Keep at 36F",
            "weight": 25000,
            "commodity_type": "Produce",
            "num_of_pieces": 12,
            "miles": 438,
            "dimensions": "53x102"
        },
    ]

def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def _filter_loads(
    origin_city: Optional[str], origin_state: Optional[str],
    destination_city: Optional[str], destination_state: Optional[str],
    pickup_date: Optional[str], equipment_type: Optional[str],
) -> List[Dict[str, Any]]:
    oc, os, dc, ds, et = map(_norm, [origin_city, origin_state, destination_city, destination_state, equipment_type])
    out: List[Dict[str, Any]] = []
    for r in LOADS:
        ro, rd = _norm(r.get("origin")), _norm(r.get("destination"))
        match = True
        if oc and oc not in ro: match = False
        if os and os not in ro: match = False
        if dc and dc not in rd: match = False
        if ds and ds not in rd: match = False
        if et and et != _norm(str(r.get("equipment_type"))): match = False
        if pickup_date and pickup_date not in (r.get("pickup_datetime") or ""): match = False
        if match:
            r2 = dict(r)
            try:
                r2["loadboard_rate"] = float(r2.get("loadboard_rate"))
            except Exception:
                pass
            out.append(r2)
    # naive ranking: prefer exact equipment match, earlier pickup first
    out.sort(key=lambda x: ( _norm(str(x.get("equipment_type"))) != et, str(x.get("pickup_datetime") or "") ))
    return out[:3]

# ---------- FMCSA Helpers ----------
def choose_carrier(payload: Any) -> Optional[Dict[str, Any]]:
    # Find {"carrier": {...}} in FMCSA responses
    if isinstance(payload, dict):
        if isinstance(payload.get("carrier"), dict):
            return payload["carrier"]
        for v in payload.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and isinstance(item.get("carrier"), dict):
                        return item["carrier"]
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("carrier"), dict):
                return item["carrier"]
    return None

def compute_verdict(carrier: Dict[str, Any]):
    allow = carrier.get("allowToOperate")
    oos   = carrier.get("outOfService")
    oos_d = carrier.get("outOfServiceDate")
    reasons, ok = [], True
    if allow == "N":
        ok = False; reasons.append("allowToOperate=N")
    if oos == "Y":
        ok = False; reasons.append(f"outOfService=Y{(' since '+oos_d) if oos_d else ''}")
    return ok, ("Active: allowed to operate and not out of service" if ok else ("; ".join(reasons) or "Not eligible"))

# ---------- API: Carriers (FMCSA) ----------
@app.get("/api/v1/carriers/find", response_model=CarrierVerdict, dependencies=[Depends(require_api_key)])
async def find_carrier(mc: str = Query(..., description="MC (docket) number digits only")):
    if not FMCSA_WEBKEY:
        raise HTTPException(500, "Server missing FMCSA_WEBKEY")
    mc_digits = mc.strip()
    if not MC_RE.match(mc_digits):
        raise HTTPException(400, "Invalid MC number format")
    url = f"{FMCSA_BASE}/carriers/docket-number/{mc_digits}"
    params = {"webKey": FMCSA_WEBKEY}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.get(url, params=params, headers={"Accept": "application/json"})
    if r.status_code == 401: raise HTTPException(502, "FMCSA authentication failed (webKey)")
    if r.status_code == 404: raise HTTPException(404, "Carrier not found for MC")
    if r.status_code >= 500: raise HTTPException(502, "FMCSA service error")
    data = r.json()
    carrier = choose_carrier(data)
    if not carrier:
        msg = data.get("content") if isinstance(data, dict) else "Carrier not found or unrecognized response"
        raise HTTPException(404, msg)
    ok, reason = compute_verdict(carrier)
    return CarrierVerdict(
        eligible=ok, reason=reason,
        mc_number=str(carrier.get("mcNumber") or mc_digits),
        dot_number=str(carrier.get("dotNumber") or ""),
        legal_name=carrier.get("legalName"),
        dba_name=carrier.get("dbaName"),
        out_of_service_date=carrier.get("outOfServiceDate"),
    )

# ---------- API: Loads (file-backed) ----------
@app.get("/api/v1/loads", dependencies=[Depends(require_api_key)])
def find_loads(
    origin_city: Optional[str] = None,
    origin_state: Optional[str] = None,
    destination_city: Optional[str] = None,
    destination_state: Optional[str] = None,
    pickup_date: Optional[str] = None,   # YYYY-MM-DD
    equipment_type: Optional[str] = None,
):
    rows = _filter_loads(origin_city, origin_state, destination_city, destination_state, pickup_date, equipment_type)
    return {"items": rows, "count": len(rows)}

# ---------- API: Offer log (JSONL) ----------
OFFERS_LOG_PATH = os.getenv("OFFERS_LOG_PATH", "/data/offers.log.jsonl")

@app.post("/api/v1/offers/log", dependencies=[Depends(require_api_key)])
def log_offer(body: OfferLog):
    os.makedirs(os.path.dirname(OFFERS_LOG_PATH), exist_ok=True)
    with open(OFFERS_LOG_PATH, "a") as f:
        f.write(json.dumps(body.dict(), separators=(",", ":")) + "\n")
    return {"ok": True}

# ---------- API: Call summary (JSONL) ----------
SUMMARY_LOG_PATH = os.getenv("SUMMARY_LOG_PATH", "/data/call_summaries.jsonl")

@app.post("/events/call-summary", dependencies=[Depends(require_api_key)])
def call_summary(body: CallSummary):
    os.makedirs(os.path.dirname(SUMMARY_LOG_PATH), exist_ok=True)
    with open(SUMMARY_LOG_PATH, "a") as f:
        f.write(json.dumps(body.dict(), separators=(",", ":")) + "\n")
    return {"ok": True}

# ---------- Metrics & simple dashboard ----------
from collections import Counter

@app.get("/metrics", dependencies=[Depends(require_api_key)])
def metrics():
    offers, summaries = [], []
    try:
        with open(OFFERS_LOG_PATH) as f:
            offers = [json.loads(x) for x in f if x.strip()]
    except Exception:
        pass
    try:
        with open(SUMMARY_LOG_PATH) as f:
            summaries = [json.loads(x) for x in f if x.strip()]
    except Exception:
        pass

    # rounds per call
    by_call = {}
    for o in offers:
        cid = o.get("call_id")
        if not cid: continue
        by_call.setdefault(cid, []).append(o)
    rounds = [len(v) for v in by_call.values()]

    outcomes = Counter([ (s.get("outcome") or "Other") for s in summaries ])
    sentiments = Counter([ (s.get("sentiment") or "Neutral") for s in summaries ])

    return {
        "totals": {
            "calls": len({s.get("call_id") for s in summaries}),
            "offers_logged": len(offers),
            "avg_rounds": (sum(rounds)/len(rounds)) if rounds else 0.0,
            "accepted": outcomes.get("Accepted",0),
            "rejected": outcomes.get("Rejected",0),
            "not_eligible": outcomes.get("Not Eligible",0)
        },
        "outcomes": outcomes,
        "sentiments": sentiments
    }

@app.get("/dash", dependencies=[Depends(require_api_key)])
def dash():
    html = """
    <!doctype html><meta charset="utf-8">
    <title>Inbound Metrics</title>
    <style>body{font-family:system-ui;margin:2rem} pre{background:#f6f6f6;padding:1rem;border-radius:8px}</style>
    <h1>Inbound Metrics</h1>
    <pre id="m">Loading…</pre>
    <script>
    fetch('/metrics',{headers:{'x-api-key':'__API_KEY__'}})
      .then(r=>r.json())
      .then(j=>{ document.getElementById('m').textContent = JSON.stringify(j,null,2) })
      .catch(e=>{ document.getElementById('m').textContent = 'Error: '+e });
    </script>
    """
    return Response(html.replace("__API_KEY__", API_KEY or ""), media_type="text/html")
