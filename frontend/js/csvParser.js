/**
 * In-Browser CSV Parser for Client-Side Preview
 * Parses only preview chunks without uploading the entire file.
 * Safely handles quoted commas, escaped quotes, and diverse line endings.
 */

function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    const nextChar = line[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        i++; // skip escaped quote
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current.trim());
  return result;
}

/**
 * Parses raw CSV text into headers and row records for preview.
 * @param {string} csvText - Raw text slice from CSV file.
 * @param {number} maxRows - Maximum rows to preview (default: 50).
 * @returns {{ headers: string[], rows: string[][], totalPreviewed: number }}
 */
function parseCSVPreview(csvText, maxRows = 50) {
  if (!csvText || typeof csvText !== 'string' || csvText.trim().length === 0) {
    throw new Error('CSV file is empty or cannot be read.');
  }

  // Normalize line breaks
  const rawLines = csvText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const validLines = rawLines.filter(l => l.trim().length > 0);

  if (validLines.length === 0) {
    throw new Error('CSV contains no data rows.');
  }

  const headers = parseCSVLine(validLines[0]);
  if (headers.length === 0 || headers.every(h => h === '')) {
    throw new Error('Could not identify valid CSV column headers.');
  }

  const previewLines = validLines.slice(1, maxRows + 1);
  const rows = previewLines.map(line => {
    const cells = parseCSVLine(line);
    // Pad or trim to match header length
    while (cells.length < headers.length) cells.push('');
    return cells.slice(0, headers.length);
  });

  return {
    headers,
    rows,
    totalPreviewed: rows.length,
    estimatedTotal: Math.max(0, validLines.length - 1),
  };
}

/**
 * Formats byte size into human readable string (KB, MB, GB).
 */
function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Support Node.js test environment and browser window globals
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { parseCSVLine, parseCSVPreview, formatFileSize };
} else {
  window.CSVParser = { parseCSVLine, parseCSVPreview, formatFileSize };
}
