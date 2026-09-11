/**
 * Frontend Unit Tests (Node test runner)
 * Validates CSV parsing, formatting, API service contracts, and grounded answer formats.
 */

const { test, describe } = require('node:test');
const assert = require('node:assert');

const { parseCSVLine, parseCSVPreview, formatFileSize } = require('../js/csvParser.js');
const { ApiService } = require('../js/apiService.js');
const { ResultRenderer } = require('../js/resultRenderer.js');

describe('CSV Parser Unit Tests', () => {
  test('parseCSVLine handles simple comma-separated values', () => {
    const line = 'Name,Department,City';
    const parsed = parseCSVLine(line);
    assert.deepStrictEqual(parsed, ['Name', 'Department', 'City']);
  });

  test('parseCSVLine handles commas inside quotes', () => {
    const line = 'Alice,"Finance, Operations",Chennai';
    const parsed = parseCSVLine(line);
    assert.deepStrictEqual(parsed, ['Alice', 'Finance, Operations', 'Chennai']);
  });

  test('parseCSVLine handles escaped quotes inside quotes', () => {
    const line = 'Bob,"Project ""Alpha""",Bangalore';
    const parsed = parseCSVLine(line);
    assert.deepStrictEqual(parsed, ['Bob', 'Project "Alpha"', 'Bangalore']);
  });

  test('parseCSVPreview parses headers and rows correctly', () => {
    const csvContent = `Name,Department,City
Alice,Billing,Chennai
Bob,Billing,Bangalore
Charlie,Engineering,Hyderabad`;

    const { headers, rows, totalPreviewed } = parseCSVPreview(csvContent, 50);

    assert.deepStrictEqual(headers, ['Name', 'Department', 'City']);
    assert.strictEqual(rows.length, 3);
    assert.strictEqual(totalPreviewed, 3);
    assert.deepStrictEqual(rows[0], ['Alice', 'Billing', 'Chennai']);
    assert.deepStrictEqual(rows[1], ['Bob', 'Billing', 'Bangalore']);
  });

  test('parseCSVPreview enforces maxRows slice limit', () => {
    const lines = ['Col1,Col2'];
    for (let i = 1; i <= 100; i++) {
      lines.push(`Val_${i},Data_${i}`);
    }
    const csvContent = lines.join('\n');

    const { rows, totalPreviewed } = parseCSVPreview(csvContent, 10);
    assert.strictEqual(rows.length, 10);
    assert.strictEqual(totalPreviewed, 10);
  });

  test('parseCSVPreview throws on empty CSV', () => {
    assert.throws(() => {
      parseCSVPreview('');
    }, /CSV file is empty/);

    assert.throws(() => {
      parseCSVPreview('   \n\n  ');
    }, /CSV file is empty/);
  });

  test('formatFileSize converts bytes correctly', () => {
    assert.strictEqual(formatFileSize(0), '0 B');
    assert.strictEqual(formatFileSize(1024), '1 KB');
    assert.strictEqual(formatFileSize(1048576), '1 MB');
    assert.strictEqual(formatFileSize(5242880), '5 MB');
  });
});

describe('API Service Contract & Grounded Chat Tests', () => {
  test('uploadCSV returns expected job contract', async () => {
    const api = new ApiService();
    api.forceMock = true;

    const mockFile = { name: 'employees.csv', size: 1024 };
    const res = await api.uploadCSV(mockFile);

    assert.ok(res.dataset_id.startsWith('ds_'));
    assert.ok(res.job_id.startsWith('job_'));
    assert.ok(res.rows_total > 0);
    assert.strictEqual(res.status, 'IN_PROGRESS');
  });

  test('getJobStatus increments rows_loaded towards rows_total', async () => {
    const api = new ApiService();
    api.forceMock = true;

    const mockFile = { name: 'test.csv', size: 500 };
    const uploadRes = await api.uploadCSV(mockFile);

    const status1 = await api.getJobStatus(uploadRes.job_id);
    assert.ok(status1.rows_loaded >= 0);
    assert.strictEqual(status1.job_id, uploadRes.job_id);
  });

  test('askQuestion returns grounded=true with Cypher for valid data queries', async () => {
    const api = new ApiService();
    api.forceMock = true;

    const resp = await api.askQuestion('How many rows are in Billing?');

    assert.strictEqual(resp.grounded, true);
    assert.ok(resp.answer.includes('Billing'));
    assert.ok(resp.cypher.includes('MATCH (r:Row)'));
    assert.ok(resp.result !== null);
  });

  test('askQuestion returns grounded=false for ungrounded/outside questions', async () => {
    const api = new ApiService();
    api.forceMock = true;

    const resp = await api.askQuestion('Who is the president of France?');

    assert.strictEqual(resp.grounded, false);
    assert.strictEqual(resp.answer, "I don't have that in the data.");
    assert.strictEqual(resp.cypher, null);
    assert.strictEqual(resp.result, null);
  });
});
