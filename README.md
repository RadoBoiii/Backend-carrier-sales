# Inbound Carrier Backend

A FastAPI-based backend service for the HappyRobot inbound carrier workflow. This service provides endpoints for FMCSA MC verification, load search, negotiation logging, call summary tracking, and a simple metrics dashboard.

## Features

- **FMCSA Integration**: Real-time carrier verification through FMCSA API
- **Load Search**: File-backed load database with flexible filtering
- **Negotiation Tracking**: Log offer rounds and call summaries
- **Metrics Dashboard**: Simple HTML dashboard for operational insights
- **Dockerized**: Runs anywhere with Docker
- **HTTPS Ready**: TLS terminated at edge on Fly.io
- **API Key Authentication**: Secure access to all sensitive endpoints

## Quick Start

### Prerequisites

- Docker
- API key for authentication
- FMCSA web key (for carrier verification)

### Local Development

1. **Build the Docker image:**
   ```bash
   docker build -t inbound-backend:latest .
   ```

2. **Run locally on port 8080:**
   ```bash
   docker run --rm -p 8080:8080 \
     -e API_KEY='bksoXZrZN5yeTaBdEaoBBDbSIe9vl-US2tome6Ia3ss' \
     -e FMCSA_WEBKEY='FMCSA_API_KEY' \
     -e LOADS_PATH=/app/loads.json \
     inbound-backend:latest
   ```

3. **Test the endpoints:**
   ```bash
   # Health check (no auth required)
   curl http://localhost:8080/healthz
   
   # Load search (API key required in the header)
   curl -H "x-api-key: bksoXZrZN5yeTaBdEaoBBDbSIe9vl-US2tome6Ia3ss" \
     "http://localhost:8080/api/v1/loads?origin_city=Chicago&destination_city=Dallas"
   
   # Log a negotiation round
   curl -H "x-api-key: bksoXZrZN5yeTaBdEaoBBDbSIe9vl-US2tome6Ia3ss" \
     -H "Content-Type: application/json" \
     -d '{"call_id":"demo-1","load_id":"L-1001","mc_number":"1515","carrier_offer":1400,"round":1}' \
     http://localhost:8080/api/v1/offers/log
   
   # Post call summary
   curl -H "x-api-key: bksoXZrZN5yeTaBdEaoBBDbSIe9vl-US2tome6Ia3ss" \
     -H "Content-Type: application/json" \
     -d '{"call_id":"demo-1","carrier_mc":"1515","load_id":"L-1001","final_price":1425,"outcome":"Accepted","sentiment":"Positive"}' \
     http://localhost:8080/events/call-summary
   
   # View metrics
   curl -H "x-api-key: bksoXZrZN5yeTaBdEaoBBDbSIe9vl-US2tome6Ia3ss" \
     http://localhost:8080/metrics
   ```

## Deployment

### Fly.io Deployment

1. **Launch the app:**
   ```bash
   fly launch --name hr-backend-restless-paper-6392 --no-deploy
   ```

2. **Set environment secrets:**
   ```bash
   fly secrets set -a hr-backend-restless-paper-6392 \
     API_KEY="bksoXZrZN5yeTaBdEaoBBDbSIe9vl-US2tome6Ia3ss" \
     FMCSA_WEBKEY="FMCSA-key"
   ```

3. **Deploy:**
   ```bash
   fly deploy -a hr-backend-restless-paper-6392
   ```

4. **Verify deployment:**
   ```bash
   curl https://hr-backend-restless-paper-6392.fly.dev/healthz
   curl -H "x-api-key: bksoXZrZN5yeTaBdEaoBBDbSIe9vl-US2tome6Ia3ss" \
     "https://hr-backend-restless-paper-6392.fly.dev/api/v1/loads?origin_city=Chicago&destination_city=Dallas"
   ```

Your app will be available at: `https://hr-backend-restless-paper-6392.fly.dev`

## API Endpoints

### Authentication
All endpoints except `/healthz` require the `x-api-key` header with a valid API key.

### Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/healthz` | Health check | No |
| GET | `/api/v1/carriers/find` | FMCSA carrier verification | Yes |
| GET | `/api/v1/loads` | Search available loads | Yes |
| POST | `/api/v1/offers/log` | Log negotiation round | Yes |
| POST | `/events/call-summary` | Post call summary | Yes |
| GET | `/metrics` | Get aggregate metrics | Yes |
| GET | `/dash` | Simple HTML dashboard | Yes |

### Detailed Endpoint Documentation

#### 1. FMCSA Carrier Verification
```http
GET /api/v1/carriers/find?mc={mc_number}
```

**Parameters:**
- `mc` (required): MC (docket) number (digits only, 4-7 digits)

**Response:**
```json
{
  "eligible": true,
  "reason": "Active: allowed to operate and not out of service",
  "mc_number": "1515",
  "dot_number": "123456",
  "legal_name": "Example Carrier LLC",
  "dba_name": "Example Trucking",
  "out_of_service_date": null
}
```

#### 2. Load Search
```http
GET /api/v1/loads?origin_city={city}&destination_city={city}&equipment_type={type}&pickup_date={date}
```

**Parameters (all optional):**
- `origin_city`: Origin city name
- `origin_state`: Origin state abbreviation
- `destination_city`: Destination city name
- `destination_state`: Destination state abbreviation
- `equipment_type`: Equipment type (e.g., "Dry Van", "Reefer")
- `pickup_date`: Pickup date in YYYY-MM-DD format

**Response:**
```json
{
  "items": [
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
    }
  ],
  "count": 1
}
```

#### 3. Log Negotiation Round
```http
POST /api/v1/offers/log
```

**Request Body:**
```json
{
  "call_id": "demo-1",
  "load_id": "L-1001",
  "mc_number": "1515",
  "carrier_offer": 1400,
  "round": 1,
  "broker_offer": 1500,
  "accepted": false
}
```

#### 4. Post Call Summary
```http
POST /events/call-summary
```

**Request Body:**
```json
{
  "call_id": "demo-1",
  "carrier_mc": "1515",
  "load_id": "L-1001",
  "final_price": 1425,
  "outcome": "Accepted",
  "sentiment": "Positive",
  "offer_history": [1400, 1450, 1425],
  "transcript_url": "https://example.com/transcript"
}
```

#### 5. Metrics
```http
GET /metrics
```

**Response:**
```json
{
  "totals": {
    "calls": 10,
    "offers_logged": 25,
    "avg_rounds": 2.5,
    "accepted": 7,
    "rejected": 2,
    "not_eligible": 1
  },
  "outcomes": {
    "Accepted": 7,
    "Rejected": 2,
    "Not Eligible": 1
  },
  "sentiments": {
    "Positive": 6,
    "Neutral": 3,
    "Negative": 1
  }
}
```

## HappyRobot Integration

### Workflow Configuration

Add these secrets to your HappyRobot workflow:

```
API_BASE = https://hr-backend-restless-paper-6392.fly.dev
API_KEY = bksoXZrZN5yeTaBdEaoBBDbSIe9vl-US2tome6Ia3ss //python -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))'
```

### Webhook Configuration

Configure webhooks with:
- **Auth**: No Auth (use header below)
- **Common Headers**:
  ```
  x-api-key: {{API_KEY}}
  Accept: application/json
  ```

### Webhook Examples

#### 1. FMCSA Verification
```http
GET {{API_BASE}}/api/v1/carriers/find
Param: mc = @mc_number
```

#### 2. Load Search
```http
GET {{API_BASE}}/api/v1/loads
Params: origin_city, origin_state, destination_city, destination_state, equipment_type, pickup_date
```

#### 3. Log Negotiation Round
```http
POST {{API_BASE}}/api/v1/offers/log
Body:
{
  "call_id": "{{run.id}}",
  "load_id": "{{ctx.load_id}}",
  "mc_number": "{{ctx.mc}}",
  "carrier_offer": {{ctx.offer}},
  "round": {{ctx.round}}
}
```

#### 4. Post Call Summary
```http
POST {{API_BASE}}/events/call-summary
Body:
{
  "call_id": "{{run.id}}",
  "carrier_mc": "{{extracted.carrier_mc}}",
  "load_id": "{{extracted.load_id}}",
  "final_price": {{extracted.final_price}},
  "outcome": "{{classified.outcome}}",
  "sentiment": "{{classified.sentiment}}",
  "offer_history": {{ctx.offer_history}}
}
```

## Data Structure

### Load Data Format

The service expects load data in JSON format at the path specified by `LOADS_PATH`:

```json
[
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
  }
]
```

**Note**: If your loads don't have pickup/delivery datetimes, simply omit `pickup_date` from the query. The API only filters by parameters you send.

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `API_KEY` | API key for authentication | - | Yes |
| `FMCSA_WEBKEY` | FMCSA API web key | - | Yes |
| `LOADS_PATH` | Path to loads data file | `/app/loads.json` | No |
| `OFFERS_LOG_PATH` | Path to offers log file | `/data/offers.log.jsonl` | No |
| `SUMMARY_LOG_PATH` | Path to call summaries log file | `/data/call_summaries.jsonl` | No |
| `HTTP_TIMEOUT` | HTTP request timeout in seconds | `6.0` | No |
| `QCMOBILE_BASE` | FMCSA API base URL | `https://mobile.fmcsa.dot.gov/qc/services` | No |

## Security

- **API Key Authentication**: All non-health routes require a valid `x-api-key` header
- **Environment Secrets**: Sensitive keys are stored as environment variables (Fly secrets in production)
- **FMCSA Proxy**: The FMCSA API key is never exposed to clients - the backend proxies requests
- **HTTPS**: TLS is handled by Fly.io at the edge
- **Input Validation**: MC numbers are validated with regex patterns

### Generate a Strong API Key

```bash
python -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))'
```

## Error Handling

| Status Code | Error | Description |
|-------------|-------|-------------|
| 401 | `{"detail":"Invalid API key"}` | Missing or incorrect API key |
| 400 | `{"detail":"Invalid MC number format"}` | Invalid MC number format |
| 404 | `{"detail":"Carrier not found"}` | FMCSA result not found |
| 502 | `{"detail":"FMCSA service error"}` | External FMCSA service error/timeout |
| 500 | `{"detail":"Server missing API_KEY"}` | Server configuration error |

## Troubleshooting

### Common Issues

1. **401 Invalid API key**
   - Ensure the `x-api-key` header is present and matches the server's `API_KEY`

2. **502/504 on FMCSA endpoints**
   - The external FMCSA service may be slow or down
   - Load search and other endpoints will still work
   - Retry the FMCSA verification later

3. **HappyRobot can't reach localhost**
   - Use the Fly.io URL for production: `https://hr-backend-restless-paper-6392.fly.dev`
   - For local testing, use a tunnel service like ngrok

4. **Load data not found**
   - Check that `LOADS_PATH` points to a valid JSON file
   - The service will fall back to demo data if the file is missing

### Logs and Monitoring

- **Offers Log**: Stored in JSONL format at `OFFERS_LOG_PATH`
- **Call Summaries**: Stored in JSONL format at `SUMMARY_LOG_PATH`
- **Metrics Dashboard**: Available at `/dash` endpoint
- **Health Check**: Available at `/healthz` endpoint

## Development

### Local Development Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run locally:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```

3. **Set environment variables:**
   ```bash
   export API_KEY="your-api-key"
   export FMCSA_WEBKEY="your-fmcsa-key"
   export LOADS_PATH="./app/loads.json"
   ```

### Project Structure

```
hr-backend/
├── app/
│   ├── main.py          # FastAPI application
│   └── loads.json       # Load data file
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Docker Compose setup
├── fly.toml            # Fly.io configuration
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## License

Internal demo/reference implementation for the take-home assignment. Use at your discretion.

---

**Note**: This service is designed for the HappyRobot inbound carrier workflow and includes integration points specifically for that use case. The FMCSA integration provides real-time carrier verification, while the load search and negotiation tracking features support the carrier outreach process.
