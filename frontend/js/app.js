/**
 * Main Application Orchestrator (Member 1 - UI & UX)
 * Initializes UI modules upon DOM load and binds cross-module callbacks.
 */

document.addEventListener('DOMContentLoaded', () => {
  console.log('Initializing Data In, Answers Out UI...');

  // 1. Initialize API Service
  const apiService = new window.ApiService();

  let activeDatasetId = null;

  // 2. Initialize Upload Manager
  const uploadManager = new window.UploadManager({
    apiService,
    onDatasetReady: (datasetId) => {
      activeDatasetId = datasetId;
      console.log('Dataset active for chat queries:', activeDatasetId);
    },
  });

  // 3. Initialize Chat Manager
  const chatManager = new window.ChatManager({
    apiService,
    getActiveDatasetId: () => activeDatasetId,
  });

  // 4. Mock toggle check in UI
  const mockToggle = document.getElementById('mock-mode-checkbox');
  if (mockToggle) {
    mockToggle.checked = apiService.forceMock;
    mockToggle.addEventListener('change', (e) => {
      apiService.forceMock = e.target.checked;
      console.log('Mock mode toggled:', apiService.forceMock);
    });
  }

  console.log('Data In, Answers Out UI ready.');
});
