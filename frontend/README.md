# Member 1 — UI & User Experience Documentation

This directory contains the complete web interface for **Data In, Answers Out** (RISE at RST Hackathon).

---

## 1. Architecture & File Structure

```
frontend/
├── index.html            # Main semantic HTML5 single-page application
├── server.js             # Zero-dependency local development server (Node.js)
├── package.json          # npm test and npm start scripts
├── README.md             # Integration guide for Member 2 (API)
├── styles/
│   ├── main.css          # Design system tokens, glassmorphism, typography, layout
│   ├── upload.css        # Drag-and-drop dropzone, file card, CSV preview table
│   ├── status.css        # Real-time progress bar, status pill badges, metrics grid
│   └── chat.css          # Chat bubbles, grounded badges, Cypher code box, result views
├── js/
│   ├── app.js            # Main application orchestrator
│   ├── csvParser.js      # In-browser fast preview CSV parser
│   ├── apiService.js     # Clean API interface layer with mock fallback
│   ├── uploadManager.js  # File selection, drag-and-drop, upload trigger, polling
│   ├── chatManager.js    # Chatbot interaction, question chips, message history
│   └── resultRenderer.js # Formats database results (tabular view, JSON tree, count summary)
└── tests/
    └── frontend.test.js  # Automated unit tests for CSV parsing, formatting, and API contracts
```

---

## 2. API Integration Specifications for Member 2

The frontend relies strictly on `js/apiService.js` to communicate with the backend. When Member 2's backend services are deployed, the frontend connects seamlessly to these 3 REST endpoints:

### Endpoint 1: CSV Upload
- **Method**: `POST`
- **Path**: `/api/upload`
- **Request Format**: `multipart/form-data` with key `file`
- **Expected Response (JSON)**:
  ```json
  {
    "dataset_id": "ds_sales_2026",
    "job_id": "job_94821",
    "rows_total": 50,
    "status": "IN_PROGRESS"
  }
  ```

### Endpoint 2: Ingestion Status Polling
- **Method**: `GET`
- **Path**: `/api/jobs/{job_id}`
- **Expected Response (JSON)**:
  ```json
  {
    "job_id": "job_94821",
    "dataset_id": "ds_sales_2026",
    "rows_total": 50,
    "rows_loaded": 35,
    "rows_failed": 0,
    "status": "IN_PROGRESS"
  }
  ```
  *(Status values supported by UI: `PENDING`, `UPLOADING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`)*.

### Endpoint 3: Grounded Chatbot Query
- **Method**: `POST`
- **Path**: `/api/chat`
- **Request Body (JSON)**:
  ```json
  {
    "question": "How many rows are in Billing?",
    "dataset_id": "ds_sales_2026"
  }
  ```
- **Expected Response (JSON)**:
  ```json
  {
    "answer": "There are 5 rows where department is 'Billing'.",
    "cypher": "MATCH (r:Row)\nWHERE toLower(toString(r.department)) = toLower($val)\nRETURN count(r) AS count",
    "result": { "count": 5, "property": "department", "value": "Billing" },
    "grounded": true
  }
  ```
- **Ungrounded Response (when answer is not in Neo4j)**:
  ```json
  {
    "answer": "I don't have that in the data.",
    "cypher": null,
    "result": null,
    "grounded": false
  }
  ```

---

## 3. How to Run Locally

### Start Local Web Server:
```bash
npm --prefix frontend start
# or:
cd frontend && node server.js
```
Then open your browser to:
```
http://localhost:3000
```
*(Or simply open `frontend/index.html` directly in any web browser).*

### Run Automated Unit Tests:
```bash
npm --prefix frontend test
```

---

## 4. Key Features Implemented

1. **Drag-and-Drop & File Picker**:
   - Accepts `.csv` files up to 50MB.
   - Highlights dropzone on drag-over.
   - Displays file name and formatted file size.
   - Allows removing and replacing selected files.

2. **Client-Side CSV Preview**:
   - Parses the first 50 rows in the browser.
   - Displays sticky header table with row numbers.
   - Handles quotes, escaped quotes, and empty files gracefully.
   - Does not upload entire file just for preview.

3. **Real-Time Ingestion Status**:
   - Dynamic progress bar with shimmer animation.
   - Metric cards: `dataset_id`, `job_id`, `rows_total`, `rows_loaded`, `rows_failed`.
   - Dynamic status badges: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`.

4. **Grounded Neo4j Chatbot**:
   - Interactive message stream with user & AI bubbles.
   - Quick-start suggestion chips for one-click questions.
   - Clear visual indicator: `Grounded in Neo4j` vs `Ungrounded / Not in Data`.
   - Syntax-styled Cypher code block with one-click copy button.
   - Interactive tabular view and expandable JSON tree view for database query results.
   - Clear conversation button.
   - Zero LLM in frontend; strictly presents backend data.
