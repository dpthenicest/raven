Here is the **fully unified, final PRD for Project Raven**, combining:

* Your **original PRD**
* The **expanded production architecture**
* The **listed search-first redesign**
* The **simplified FastAPI + PostgreSQL-only system**

Everything is now aligned into a **single, cohesive, build-ready document**.

---

# 🐦 Project Raven: B2C Power Supply & Tariff Band Identifier

**"Transparency for Every Megawatt."**

---

# 0. Executive Overview

**Project Raven** is a **geospatial + structured data intelligence platform** that enables Nigerian users to:

* Instantly identify **electricity tariff bands (A–E)**
* Search using **known locations (primary experience)**
* Fall back to **map-based geospatial detection**
* Compare **official vs real-world power supply (Raven Score)**

---

## 🎯 Core Problem

> Nigerians make housing and business decisions without reliable electricity data.

---

## 💡 Core Solution

A **dual-engine system**:

1. **Listed Search Engine (Primary)**

   * Fast, autocomplete-based
   * Built on structured feeder addresses

2. **Geospatial Engine (Fallback)**

   * Powered by PostGIS
   * Handles unknown or unmapped locations

---

# 1. Technical Architecture (Final)

## 1.1 High-Level Architecture

```id="arch_final_01"
Frontend (Next.js / React Native)
        │
        ▼
FastAPI Backend (Async)
        │
        ▼
PostgreSQL + PostGIS
        │
        ▼
External Integrations:
- Google Maps API (Geocoding)
- Interswitch (Payments)
- NERC PDFs (Admin Upload)
```

---

## 1.2 Architecture Decisions

### Backend

* **FastAPI (single service layer)**
* Async endpoints for performance

### Database

* **PostgreSQL + PostGIS (MANDATORY)**

  * Full-text search (TSVECTOR)
  * Geospatial queries (POLYGON)

### Removed Components

| Component       | Reason               |
| --------------- | -------------------- |
| Redis           | Simplify MVP         |
| Background jobs | Avoid infra overhead |

---

## 1.3 Tradeoffs

| Tradeoff      | Impact                         | Mitigation           |
| ------------- | ------------------------------ | -------------------- |
| No cache      | Slightly slower repeat queries | Strong DB indexing   |
| No async jobs | Blocking admin tasks           | Admin-only execution |

---

# 2. Database Design (Final)

## 2.1 Core Tables

### **users**

* `id`, `email`, `oauth_id`
* `credits` (default = 1)
* `role` (USER, ADMIN)
* `created_at`, `last_login_at`

---

### **discos**

* `id`, `name`, `code`, `path`

---

### **feeders (CORE TABLE)**

| Column                  | Type                  | Description             |
| ----------------------- | --------------------- | ----------------------- |
| `id`                    | UUID                  | Primary key             |
| `disco_id`              | UUID                  | FK                      |
| `name`                  | String                | Feeder name             |
| `tariff_band`           | Enum(A–E)             | Official band           |
| `formatted_address`     | String                | Main searchable address |
| `aliases`               | JSONB                 | Alternative names       |
| `search_vector`         | TSVECTOR              | Full-text search        |
| `state`                 | String                | Region                  |
| `longitude`, `latitude` | Float                 | Centroid                |
| **`bounds`**            | **GEOMETRY(POLYGON)** | Map search              |
| `cap_kwh`               | Float                 | NERC cap                |
| `confidence_score`      | Float                 | Data accuracy           |
| `last_updated`          | Timestamp             | Freshness               |

---

### **searches**

* `id`, `user_id`
* `lat`, `lng`
* `found_band`
* `device_type`
* `search_source` (LIST | MAP)

---

### **ratings_reviews**

* `id`, `user_id`, `feeder_id`
* `stars`, `actual_hours`
* `reviews`, `questions`
* `upvotes`, `downvotes`
* `is_verified`

---

### **transactions**

* `id`, `user_id`
* `txn_ref`
* `amount`, `status`

---

## 2.2 Indexing Strategy

```sql id="final_idx_01"
-- Full-text search
CREATE INDEX idx_feeders_search ON feeders USING GIN(search_vector);

-- Geospatial
CREATE INDEX idx_feeders_bounds ON feeders USING GIST(bounds);

-- Performance
CREATE INDEX idx_feeders_name ON feeders(name);
CREATE INDEX idx_searches_user_id ON searches(user_id);
```

---

## 2.3 Full-Text Search Setup

```sql id="final_search_01"
ALTER TABLE feeders ADD COLUMN search_vector tsvector;

UPDATE feeders
SET search_vector =
    to_tsvector('english',
        coalesce(name,'') || ' ' ||
        coalesce(formatted_address,'')
    );
```

---

## 2.4 Data Integrity Rules

* Tariff band must be **A–E**
* `actual_hours` must be **0–24**
* Credits cannot go negative
* Each feeder belongs to one DisCo

---

# 3. Core Product Flows (Final)

---

## 3.1 Authentication Flow (OAuth2)

1. User clicks “Sign in with Google”
2. Redirect → `/auth/login/google`
3. Callback → `/auth/callback`
4. Backend:

   * Exchange code
   * Create/fetch user
   * Assign **1 free credit**
5. Issue JWT

---

## 3.2 Listed Search Flow (PRIMARY EXPERIENCE)

### 🔍 This is the DEFAULT way users interact

---

### Flow:

1. User types location
   *(e.g., “Rumuola Port Harcourt”)*

2. Frontend calls:

```http
GET /feeders/suggest?q=rumuola
```

3. Backend query:

```sql id="final_search_02"
SELECT id, name, formatted_address, tariff_band
FROM feeders
WHERE search_vector @@ plainto_tsquery(:query)
ORDER BY ts_rank(search_vector, plainto_tsquery(:query)) DESC
LIMIT 10;
```

4. User selects a result

5. Fetch details:

```http
GET /feeders/{id}/details
```

---

### Response Includes:

* Feeder name
* Tariff band
* Expected supply hours
* Raven Score
* Reviews

---

## 3.3 Map Search Flow (FALLBACK ONLY)

Triggered when:

* No listed results
* User explicitly chooses map

---

### Flow:

1. User drops pin
2. Request:

```json
{ "latitude": ..., "longitude": ... }
```

3. Query:

```sql id="final_geo_01"
SELECT id, name, tariff_band
FROM feeders
WHERE ST_Contains(bounds, ST_SetSRID(ST_Point(:lng, :lat), 4326));
```

---

### Fallback:

```sql id="final_geo_02"
ST_DWithin(bounds, point, radius)
```

---

### Response:

* Closest feeder
* Tariff band
* Confidence level

---

## 3.4 Credit Usage Model

| Action                  | Credits |
| ----------------------- | ------- |
| Listed search (suggest) | FREE    |
| View feeder details     | 1       |
| Map search              | 1       |

---

# 4. Core Intelligence Layer

---

## 4.1 Raven Score

```
Raven Score = Weighted Avg(actual_hours)
```

### Weight Factors:

* Recency
* Verification
* Upvotes/downvotes

---

## 4.2 Confidence Levels

| Level  | Meaning             |
| ------ | ------------------- |
| HIGH   | Exact polygon match |
| MEDIUM | Near feeder         |
| LOW    | Weak proximity      |

---

## 4.3 Fraud Detection

* Prevent duplicate submissions (24h)
* Detect extreme outliers
* Flag suspicious feeders

---

# 5. API Design (Final)

---

## 5.1 Authentication

* `GET /auth/login/{provider}`
* `GET /auth/callback`
* `GET /users/me`

---

## 5.2 Search & Discovery

### Autocomplete (PRIMARY)

```
GET /feeders/suggest?q=...
```

---

### Feeder Details

```
GET /feeders/{id}/details
```

---

### Map Search

```
POST /search/coordinate
```

---

## 5.3 Reviews

* `POST /reviews`
* `GET /reviews/feeder/{id}`

---

## 5.4 Payments

* `POST /payments/initialize`
* `GET /payments/verify/{txn_ref}`

---

## 5.5 Admin

* `POST /admin/parse-nerc`

---

# 6. Data Pipeline (NERC PDFs)

---

## 6.1 Parsing Strategy

```python
import fitz

def parse_nerc_document(pdf_content):
    doc = fitz.open(stream=pdf_content, filetype="pdf")
```

---

## 6.2 Pipeline Flow

```
PDF → Extract → Clean → Validate → Geocode → Store
```

---

## 6.3 Data Quality Rules

* Missing feeder → discard
* Invalid band → log
* Outliers → flag

---

# 7. Payment System

---

## Credit Packs

| Pack     | Price  | Credits |
| -------- | ------ | ------- |
| Starter  | ₦500   | 5       |
| Standard | ₦2,000 | 25      |
| Pro      | ₦5,000 | 80      |

---

## Security

* Server-side verification
* Idempotent updates
* Retry failed verification

---

# 8. Admin System

* Upload NERC PDFs
* Edit feeder data
* Add aliases
* Moderate reviews

---

# 9. Performance Optimization (No Redis)

---

## Database Optimization

* GIN index (search)
* GIST index (geospatial)
* Query limits

---

## API Optimization

* Async endpoints
* Field selection
* Pagination

---

# 10. Observability & Monitoring

* Logging (Loguru / ELK)
* Metrics (Prometheus)
* Alerts:

  * Latency > 500ms
  * DB overload

---

# 11. Security & Compliance

* HTTPS
* JWT rotation
* Input validation
* NDPR compliance

---

# 12. Deployment Strategy

* Dockerized FastAPI
* PostgreSQL hosting
* Environments:

  * Dev
  * Staging
  * Production

---

# 13. User Experience Design

---

## First-Time User

* 1 free search
* Instant result
* Upsell credits

---

## Power Users

* Bulk search (future)
* Saved locations

---

## Offline Handling

* Show last known result

---

# 14. Success Metrics

| Metric              | Target  |
| ------------------- | ------- |
| Search success rate | 90%+    |
| Map fallback usage  | < 20%   |
| Latency             | < 500ms |
| Accuracy            | 100%    |

---

# 15. Risks & Mitigation

| Risk                 | Mitigation         |
| -------------------- | ------------------ |
| Poor geospatial data | Manual admin fixes |
| Fake reviews         | Weighted scoring   |
| Payment failures     | Retry logic        |

---

# 16. Future Roadmap

---

## Phase 2

* AI outage prediction
* Notifications

## Phase 3

* PropTech API
* Real estate integrations

---

# 🔥 Final Positioning

**Project Raven is:**

* A **search engine for electricity reliability**
* A **decision engine for housing**
* A **data infrastructure layer for Nigeria**
