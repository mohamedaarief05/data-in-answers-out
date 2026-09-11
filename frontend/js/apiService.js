/**
 * API Service Integration Layer (Member 1 <-> Member 2)
 * Connects the frontend to the backend REST endpoints.
 * Includes a simulated mock mode when the API is offline during development.
 */

class ApiService {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl;
    // Check if query param ?mock=true is passed or auto-fallback
    const urlParams = typeof window !== 'undefined' && window.location ? new URLSearchParams(window.location.search) : null;
    this.forceMock = urlParams ? urlParams.get('mock') === 'true' : false;
    this.activeJob = null;
  }

  /**
   * Upload CSV file to backend.
   * Endpoint: POST /api/upload
   * Expected Request: multipart/form-data with 'file'
   * Expected Response: { dataset_id: string, job_id: string, rows_total: number, status: string }
   */
  async uploadCSV(file) {
    if (this.forceMock) {
      return this._mockUpload(file);
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${this.baseUrl}/api/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed with HTTP ${response.status}`);
      }

      const data = await response.json();
      this.activeJob = data;
      return data;
    } catch (err) {
      console.warn('Backend API unavailable, falling back to simulated integration mode:', err.message);
      return this._mockUpload(file);
    }
  }

  /**
   * Poll ingestion job status.
   * Endpoint: GET /api/jobs/{job_id}
   * Expected Response: { job_id, dataset_id, rows_total, rows_loaded, rows_failed, status }
   */
  async getJobStatus(jobId) {
    if (this.forceMock || (this.activeJob && this.activeJob.isMock)) {
      return this._mockJobStatus(jobId);
    }

    try {
      const response = await fetch(`${this.baseUrl}/api/jobs/${jobId}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch job status: HTTP ${response.status}`);
      }
      return await response.json();
    } catch (err) {
      return this._mockJobStatus(jobId);
    }
  }

  /**
   * Send question to grounded chatbot.
   * Endpoint: POST /api/chat
   * Expected Request: { question: string, dataset_id?: string }
   * Expected Response: { answer: string, cypher: string|null, result: any, grounded: boolean }
   */
  async askQuestion(question, datasetId = null) {
    if (this.forceMock || (this.activeJob && this.activeJob.isMock)) {
      return this._mockChat(question, datasetId);
    }

    try {
      const response = await fetch(`${this.baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, dataset_id: datasetId }),
      });

      if (!response.ok) {
        throw new Error(`Chat request failed: HTTP ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.warn('Chat endpoint unavailable, using demo simulation:', err.message);
      return this._mockChat(question, datasetId);
    }
  }

  /* -------------------------------------------------------------
     Isolated Mock Simulation for Hackathon UI Development
     ------------------------------------------------------------- */

  _mockUpload(file) {
    const datasetId = `ds_${Date.now().toString(36)}`;
    const jobId = `job_${Math.random().toString(36).substring(2, 9)}`;
    const estimatedRows = Math.floor(Math.random() * 80) + 20;

    this.activeJob = {
      dataset_id: datasetId,
      job_id: jobId,
      rows_total: estimatedRows,
      rows_loaded: 0,
      rows_failed: 0,
      status: 'IN_PROGRESS',
      isMock: true,
      created_at: Date.now(),
    };

    return new Promise(resolve => {
      setTimeout(() => resolve({
        dataset_id: datasetId,
        job_id: jobId,
        rows_total: estimatedRows,
        status: 'IN_PROGRESS',
      }), 600);
    });
  }

  _mockJobStatus(jobId) {
    if (!this.activeJob) {
      return {
        job_id: jobId,
        dataset_id: 'unknown',
        rows_total: 0,
        rows_loaded: 0,
        rows_failed: 0,
        status: 'COMPLETED',
      };
    }

    // Advance loaded count
    const increment = Math.ceil(this.activeJob.rows_total / 4);
    this.activeJob.rows_loaded = Math.min(
      this.activeJob.rows_total,
      this.activeJob.rows_loaded + increment
    );

    if (this.activeJob.rows_loaded >= this.activeJob.rows_total) {
      this.activeJob.status = 'COMPLETED';
    } else {
      this.activeJob.status = 'IN_PROGRESS';
    }

    return Promise.resolve({ ...this.activeJob });
  }

  _mockChat(question, datasetId) {
    const q = question.toLowerCase();

    return new Promise(resolve => {
      setTimeout(() => {
        // Deterministic Grounded Pattern Matches matching Member 3's Neo4j loader
        if (q.includes('billing')) {
          resolve({
            answer: "There are 5 rows where department is 'Billing'.",
            cypher: "MATCH (r:Row)\nWHERE toLower(toString(r.department)) = toLower($val)\nRETURN count(r) AS count",
            result: { count: 5, property: "department", value: "Billing" },
            grounded: true,
          });
        } else if (q.includes('chennai')) {
          resolve({
            answer: "There are 3 rows where city is 'Chennai'.",
            cypher: "MATCH (r:Row)\nWHERE toLower(toString(r.city)) = toLower($val)\nRETURN count(r) AS count",
            result: { count: 3, property: "city", value: "Chennai" },
            grounded: true,
          });
        } else if (q.includes('show rows') || q.includes('list rows')) {
          resolve({
            answer: "Found 2 rows where department is 'Billing'.",
            cypher: "MATCH (r:Row)\nWHERE toLower(toString(r.department)) = toLower($val)\nRETURN properties(r) AS row_props\nLIMIT 10",
            result: [
              { name: "Alice Smith", department: "Billing", city: "Chennai", salary: 85000 },
              { name: "Bob Johnson", department: "Billing", city: "Bangalore", salary: 92000 }
            ],
            grounded: true,
          });
        } else if (q.includes('how many rows') || q.includes('total rows') || q.includes('count rows')) {
          resolve({
            answer: "There are 48 total rows in the data.",
            cypher: "MATCH (r:Row)\nRETURN count(r) AS count",
            result: { count: 48 },
            grounded: true,
          });
        } else {
          // Strict Ungrounded Refusal matching Member 3 requirement
          resolve({
            answer: "I don't have that in the data.",
            cypher: null,
            result: null,
            grounded: false,
          });
        }
      }, 500);
    });
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ApiService };
} else {
  window.ApiService = ApiService;
}
