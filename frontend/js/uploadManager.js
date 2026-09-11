/**
 * Upload Manager: Handles File Drop, In-Browser Preview,
 * Upload Triggers, and Ingestion Progress Polling.
 */

class UploadManager {
  constructor({ apiService, onDatasetReady }) {
    this.apiService = apiService;
    this.onDatasetReady = onDatasetReady;
    this.currentFile = null;
    this.currentDatasetId = null;
    this.pollInterval = null;

    this.cacheDOMElements();
    this.bindEvents();
  }

  cacheDOMElements() {
    this.dropzone = document.getElementById('dropzone');
    this.fileInput = document.getElementById('file-input');
    this.selectFileBtn = document.getElementById('select-file-btn');
    this.uploadBtn = document.getElementById('upload-btn');

    this.selectedFileCard = document.getElementById('selected-file-card');
    this.fileNameEl = document.getElementById('file-name');
    this.fileSizeEl = document.getElementById('file-size');
    this.removeFileBtn = document.getElementById('remove-file-btn');

    this.previewContainer = document.getElementById('preview-container');
    this.previewTableHead = document.getElementById('preview-thead');
    this.previewTableBody = document.getElementById('preview-tbody');
    this.previewRowCountEl = document.getElementById('preview-row-count');
    this.uploadAlert = document.getElementById('upload-alert');

    // Progress & Status Elements
    this.statusCard = document.getElementById('status-card');
    this.statusBadge = document.getElementById('status-badge');
    this.progressBar = document.getElementById('progress-bar-fill');
    this.metricDataset = document.getElementById('metric-dataset');
    this.metricJob = document.getElementById('metric-job');
    this.metricTotal = document.getElementById('metric-total');
    this.metricLoaded = document.getElementById('metric-loaded');
    this.metricFailed = document.getElementById('metric-failed');
  }

  bindEvents() {
    // Dropzone click opens file dialog
    this.selectFileBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.fileInput.click();
    });

    this.dropzone.addEventListener('click', () => {
      this.fileInput.click();
    });

    this.fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) this.handleFileSelection(file);
    });

    // Drag-and-drop
    ['dragenter', 'dragover'].forEach(eventName => {
      this.dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.dropzone.classList.add('drag-active');
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      this.dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.dropzone.classList.remove('drag-active');
      }, false);
    });

    this.dropzone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const file = dt.files[0];
      if (file) this.handleFileSelection(file);
    });

    // Remove file
    this.removeFileBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.clearFile();
    });

    // Upload button
    this.uploadBtn.addEventListener('click', () => {
      this.startUpload();
    });
  }

  handleFileSelection(file) {
    this.hideAlert();

    // Validate CSV extension
    if (!file.name.toLowerCase().endsWith('.csv') && file.type !== 'text/csv') {
      this.showAlert('Please select a valid CSV file (.csv format only).', 'error');
      return;
    }

    this.currentFile = file;

    // Update File Card info
    this.fileNameEl.textContent = file.name;
    const formatFn = window.CSVParser ? window.CSVParser.formatFileSize : (b => `${b} B`);
    this.fileSizeEl.textContent = formatFn(file.size);

    this.dropzone.style.display = 'none';
    this.selectedFileCard.style.display = 'flex';
    this.uploadBtn.disabled = false;

    // Read initial slice for fast in-browser preview (reads up to 64KB first)
    const previewSlice = file.slice(0, 65536);
    const reader = new FileReader();

    reader.onload = (e) => {
      try {
        const text = e.target.result;
        const parseFn = window.CSVParser ? window.CSVParser.parseCSVPreview : null;
        if (!parseFn) throw new Error('CSV parser not loaded');

        const { headers, rows, totalPreviewed } = parseFn(text, 50);
        this.renderPreviewTable(headers, rows, totalPreviewed);
      } catch (parseErr) {
        this.showAlert(`Preview Warning: ${parseErr.message}`, 'warning');
        this.previewContainer.style.display = 'none';
      }
    };

    reader.onerror = () => {
      this.showAlert('Could not read file for preview.', 'error');
    };

    reader.readAsText(previewSlice);
  }

  renderPreviewTable(headers, rows, totalPreviewed) {
    this.previewTableHead.innerHTML = '';
    this.previewTableBody.innerHTML = '';

    // Header Row with Index
    const headerTr = document.createElement('tr');
    const thIdx = document.createElement('th');
    thIdx.className = 'row-index-cell';
    thIdx.textContent = '#';
    headerTr.appendChild(thIdx);

    headers.forEach(h => {
      const th = document.createElement('th');
      th.textContent = h || 'unnamed';
      headerTr.appendChild(th);
    });
    this.previewTableHead.appendChild(headerTr);

    // Data Rows
    rows.forEach((row, i) => {
      const tr = document.createElement('tr');
      const tdIdx = document.createElement('td');
      tdIdx.className = 'row-index-cell';
      tdIdx.textContent = i + 1;
      tr.appendChild(tdIdx);

      row.forEach(cellVal => {
        const td = document.createElement('td');
        td.textContent = cellVal;
        tr.appendChild(td);
      });
      this.previewTableBody.appendChild(tr);
    });

    this.previewRowCountEl.textContent = `Showing first ${totalPreviewed} rows`;
    this.previewContainer.style.display = 'flex';
  }

  clearFile() {
    this.currentFile = null;
    this.fileInput.value = '';
    this.selectedFileCard.style.display = 'none';
    this.previewContainer.style.display = 'none';
    this.dropzone.style.display = 'flex';
    this.uploadBtn.disabled = true;
    this.hideAlert();
  }

  async startUpload() {
    if (!this.currentFile) return;

    this.uploadBtn.disabled = true;
    this.uploadBtn.textContent = 'Uploading...';
    this.statusCard.style.display = 'flex';
    this.updateStatusUI({ status: 'UPLOADING', rows_loaded: 0, rows_total: 0, rows_failed: 0 });

    try {
      const uploadResult = await this.apiService.uploadCSV(this.currentFile);
      this.currentDatasetId = uploadResult.dataset_id;

      if (this.onDatasetReady) {
        this.onDatasetReady(this.currentDatasetId);
      }

      this.updateStatusUI({
        dataset_id: uploadResult.dataset_id,
        job_id: uploadResult.job_id,
        rows_total: uploadResult.rows_total,
        status: uploadResult.status || 'IN_PROGRESS',
      });

      // Start polling for ingestion progress
      this.startPolling(uploadResult.job_id);
    } catch (err) {
      this.showAlert(`Upload failed: ${err.message}`, 'error');
      this.updateStatusUI({ status: 'FAILED' });
      this.uploadBtn.disabled = false;
      this.uploadBtn.textContent = 'Upload to Pipeline';
    }
  }

  startPolling(jobId) {
    if (this.pollInterval) clearInterval(this.pollInterval);

    this.pollInterval = setInterval(async () => {
      try {
        const statusData = await this.apiService.getJobStatus(jobId);
        this.updateStatusUI(statusData);

        if (statusData.status === 'COMPLETED' || statusData.status === 'FAILED') {
          clearInterval(this.pollInterval);
          this.uploadBtn.disabled = false;
          this.uploadBtn.textContent = 'Upload Another CSV';
        }
      } catch (err) {
        console.warn('Status polling error:', err);
      }
    }, 1200);
  }

  updateStatusUI(data) {
    const status = (data.status || 'PENDING').toUpperCase();

    // Badge styling
    this.statusBadge.textContent = status;
    this.statusBadge.className = 'badge-status';

    if (status === 'COMPLETED') {
      this.statusBadge.classList.add('badge-completed');
    } else if (status === 'FAILED') {
      this.statusBadge.classList.add('badge-failed');
    } else if (status === 'IN_PROGRESS' || status === 'UPLOADING') {
      this.statusBadge.classList.add('badge-in-progress');
    } else {
      this.statusBadge.classList.add('badge-pending');
    }

    // Metrics
    if (data.dataset_id) this.metricDataset.textContent = data.dataset_id;
    if (data.job_id) this.metricJob.textContent = data.job_id;
    if (data.rows_total !== undefined) this.metricTotal.textContent = data.rows_total;
    if (data.rows_loaded !== undefined) this.metricLoaded.textContent = data.rows_loaded;
    if (data.rows_failed !== undefined) this.metricFailed.textContent = data.rows_failed;

    // Progress Bar
    const total = data.rows_total || 0;
    const loaded = data.rows_loaded || 0;
    const percentage = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : (status === 'COMPLETED' ? 100 : 15);
    this.progressBar.style.width = `${percentage}%`;
  }

  showAlert(msg, type = 'error') {
    this.uploadAlert.textContent = msg;
    this.uploadAlert.className = `upload-alert alert-${type}`;
    this.uploadAlert.style.display = 'flex';
  }

  hideAlert() {
    this.uploadAlert.style.display = 'none';
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { UploadManager };
} else {
  window.UploadManager = UploadManager;
}
