# Feeder Admin API Documentation

## New Admin Endpoints for Feeder Management

### 1. Create Feeder Manually
**POST** `/admin/feeders`

Manually add a feeder entry when automatic parsing fails or for custom entries.

**Request Body:**
```json
{
  "disco_code": "PHEDC",
  "name": "AMADI AMA",
  "business_unit": "ALPHA 1",
  "tariff_band": "C",
  "state": "RIVERS",
  "cap_kwh": 555.0,
  "latitude": 4.8156,
  "longitude": 7.0498,
  "formatted_address": "Port Harcourt, Rivers State"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "disco_code": "PHEDC",
  "name": "AMADI AMA",
  "business_unit": "ALPHA 1",
  "tariff_band": "C",
  "state": "RIVERS",
  "cap_kwh": 555.0,
  "latitude": 4.8156,
  "longitude": 7.0498,
  "formatted_address": "Port Harcourt, Rivers State",
  "confidence_score": 1.0,
  "aliases": null,
  "raven_score": null
}
```

### 2. Update Feeder Information
**PUT** `/admin/feeders/{feeder_id}`

Update feeder details including band, cap, location, or address. Useful for correcting "UNKNOWN" bands.

**Request Body (all fields optional):**
```json
{
  "tariff_band": "B",
  "cap_kwh": 428.0,
  "latitude": 5.0123,
  "longitude": 7.9876,
  "formatted_address": "Updated Address",
  "business_unit": "UYO",
  "state": "AKWA IBOM"
}
```

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "disco_code": "PHEDC",
  "name": "NWANIBA",
  "business_unit": "UYO",
  "tariff_band": "B",
  "state": "AKWA IBOM",
  "cap_kwh": 428.0,
  "latitude": 5.0123,
  "longitude": 7.9876,
  "formatted_address": "Updated Address",
  "confidence_score": 1.0,
  "aliases": null,
  "raven_score": null
}
```

### 3. Get Feeder Details
**GET** `/admin/feeders/{feeder_id}`

Retrieve complete feeder information by ID.

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "disco_code": "PHEDC",
  "name": "BARRACKS",
  "business_unit": "ALPHA 1",
  "tariff_band": "-",
  "state": "RIVERS",
  "cap_kwh": 646.0,
  "latitude": null,
  "longitude": null,
  "formatted_address": null,
  "confidence_score": 1.0,
  "aliases": null,
  "raven_score": null
}
```

## Enhanced NERC PDF Parsing Response

The PDF parsing endpoints now return detailed information about rejected rows:

**POST** `/admin/parse-nerc` or **POST** `/admin/parse-nerc/{disco_code}/fetch`

**Enhanced Response:**
```json
{
  "parsed": 211,
  "saved": 209,
  "skipped": 2,
  "pages": [
    {
      "number": 1,
      "total_rows": 43,
      "rows_extracted": 30,
      "fallback_count": 2
    },
    {
      "number": 2,
      "total_rows": 52,
      "rows_extracted": 47,
      "fallback_count": 0
    }
  ],
  "rejected_rows": [
    {
      "page": 1,
      "row": 15,
      "state": "AKWA IBOM",
      "business_unit": "UYO",
      "feeder_name": "NWANIBA",
      "raw_text": "AKWA IBOM | UYO | NWANIBA | 428",
      "reason": "Missing required fields or invalid data"
    },
    {
      "page": 3,
      "row": 26,
      "state": "CROSS RIVER",
      "business_unit": "CALABAR AMIKA",
      "feeder_name": null,
      "raw_text": "CROSS RIVER | CALABAR AMIKA | A | 468 Page | 2",
      "reason": "Missing required fields or invalid data"
    }
  ],
  "disco": "Port Harcourt Electricity Distribution Plc",
  "message": "Successfully imported 209 feeders for Port Harcourt Electricity Distribution Plc"
}
```

## Workflow for Handling Rejected Rows

1. **Parse PDF** - Use `/admin/parse-nerc/{disco_code}/fetch`
2. **Review rejected_rows** - Check which rows failed and why
3. **Manually create missing feeders** - Use `POST /admin/feeders` with correct data
4. **Update UNKNOWN bands** - Use `PUT /admin/feeders/{feeder_id}` to fix fallback bands

## Example: Fixing UNKNOWN Bands

```bash
# 1. Find feeders with UNKNOWN band (-)
GET /feeders?disco_code=PHEDC&tariff_band=-

# 2. Update each feeder with correct band
PUT /admin/feeders/{feeder_id}
{
  "tariff_band": "C"
}
```

## Page Metadata Fields

- `number`: Page number in PDF
- `total_rows`: Total rows detected on page
- `rows_extracted`: Successfully extracted feeders
- `fallback_count`: Number of feeders using "UNKNOWN" fallback band

## Rejected Row Fields

- `page`: Page number where row was found
- `row`: Row index on that page
- `state`: Detected state (or last known)
- `business_unit`: Detected business unit (or last known)
- `feeder_name`: Detected feeder name (null if empty)
- `raw_text`: Raw OCR text for debugging
- `reason`: Why the row was rejected

## Notes

- All admin endpoints require authentication with admin role
- Feeder IDs are UUIDs
- Tariff bands must be one of: A, B, C, D, E, or "-" (unknown)
- The "-" band indicates missing/undetected band data that needs manual review
- Coordinates should be in decimal degrees (latitude, longitude)
- The `fallback_count` indicates rows where band was missing and set to "-"

---

## Geocoding Endpoints

### 4. Geocode All Feeders
**POST** `/admin/geocode/all`

Geocode all feeders in the database using Google Maps API. This will update latitude, longitude, formatted_address, and bounds for all feeders.

**Note:** This operation may take a while depending on the number of feeders.

**Response:** `200 OK`
```json
{
  "total": 500,
  "processed": 485,
  "failed": 15,
  "message": "Geocoded 485 out of 500 feeders"
}
```

### 5. Geocode Feeders by DisCo
**POST** `/admin/geocode/disco/{disco_code}`

Geocode all feeders for a specific DisCo using Google Maps API.

**Path Parameters:**
- `disco_code`: DisCo code (e.g., "PHEDC", "EKEDC")

**Response:** `200 OK`
```json
{
  "disco_code": "PHEDC",
  "total": 211,
  "processed": 205,
  "failed": 6,
  "message": "Geocoded 205 out of 211 feeders for PHEDC"
}
```

### 6. Geocode Single Feeder
**POST** `/admin/geocode/feeder/{feeder_id}`

Geocode a single feeder using Google Maps API.

**Path Parameters:**
- `feeder_id`: UUID of the feeder

**Response:** `200 OK`
```json
{
  "feeder_id": "uuid",
  "name": "AMADI AMA",
  "latitude": 4.8156,
  "longitude": 7.0498,
  "formatted_address": "Port Harcourt, Rivers State, Nigeria",
  "message": "Feeder geocoded successfully"
}
```

**Error Response:** `500 Internal Server Error`
```json
{
  "detail": "Failed to geocode feeder. Check logs for details."
}
```

## Geocoding Details

### How Geocoding Works

1. **Address Construction**: Combines feeder name, state, and "Nigeria" to create a search address
   - Example: "AMADI AMA, RIVERS, Nigeria"

2. **Google Maps API Call**: Sends the address to Google Maps Geocoding API

3. **Data Extraction**: Retrieves:
   - `latitude` and `longitude`: Precise coordinates
   - `formatted_address`: Google's standardized address
   - `bounds`: Geographic bounding box (stored as PostGIS POLYGON)

4. **Database Update**: Updates the feeder record with all geocoding data

### Configuration

Ensure `GOOGLE_MAPS_API_KEY` is set in your `.env` file:

```env
GOOGLE_MAPS_API_KEY=your_api_key_here
```

### Geocoding Workflow

1. **Import feeders from NERC PDF**
   ```bash
   POST /admin/parse-nerc/PHEDC/fetch
   ```

2. **Geocode all feeders for that DisCo**
   ```bash
   POST /admin/geocode/disco/PHEDC
   ```

3. **Review failed geocoding attempts** (check logs)

4. **Manually geocode specific feeders if needed**
   ```bash
   POST /admin/geocode/feeder/{feeder_id}
   ```

### Geocoding Best Practices

- Run geocoding after importing feeders from NERC PDFs
- Use disco-specific geocoding for better control and monitoring
- Check logs for failed geocoding attempts
- Failed geocoding usually indicates:
  - Invalid or incomplete feeder names
  - Missing state information
  - Google Maps API quota exceeded
  - Network connectivity issues

### Rate Limits

Google Maps Geocoding API has rate limits. Consider:
- Using disco-specific geocoding to process in batches
- Adding delays between requests if hitting rate limits
- Monitoring your API quota in Google Cloud Console

