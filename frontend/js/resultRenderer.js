/**
 * Result Renderer: Formats Cypher Queries and Graph Database Results
 * Supports interactive tabular views, count summaries, and expandable JSON inspector.
 */

class ResultRenderer {
  /**
   * Generates a Cypher query card with a copy-to-clipboard button.
   * @param {string} cypher - The Cypher query returned from the backend.
   * @returns {HTMLElement}
   */
  static createCypherBlock(cypher) {
    const container = document.createElement('div');
    container.className = 'cypher-block';

    const header = document.createElement('div');
    header.className = 'cypher-header';

    const label = document.createElement('span');
    label.className = 'cypher-label';
    label.textContent = 'Generated Cypher (Neo4j)';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
      </svg>
      <span>Copy</span>
    `;

    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(cypher);
        copyBtn.classList.add('copied');
        copyBtn.querySelector('span').textContent = 'Copied!';
        setTimeout(() => {
          copyBtn.classList.remove('copied');
          copyBtn.querySelector('span').textContent = 'Copy';
        }, 2000);
      } catch (err) {
        console.warn('Clipboard write failed:', err);
      }
    });

    header.appendChild(label);
    header.appendChild(copyBtn);

    const code = document.createElement('pre');
    code.className = 'cypher-code';
    code.textContent = cypher;

    container.appendChild(header);
    container.appendChild(code);
    return container;
  }

  /**
   * Generates a database result visualizer with Table and JSON views.
   * @param {any} result - The result payload from Neo4j.
   * @returns {HTMLElement|null}
   */
  static createResultVisualizer(result) {
    if (result === undefined || result === null) {
      return null;
    }

    const container = document.createElement('div');
    container.className = 'result-section';

    // 1. Single scalar or count result: { count: 5 }
    if (typeof result === 'object' && result !== null && !Array.isArray(result) && Object.keys(result).length <= 3 && 'count' in result) {
      const countBox = document.createElement('div');
      countBox.style.padding = '0.5rem 0.75rem';
      countBox.style.background = 'rgba(6, 182, 212, 0.1)';
      countBox.style.border = '1px solid rgba(6, 182, 212, 0.25)';
      countBox.style.borderRadius = '8px';
      countBox.style.display = 'flex';
      countBox.style.alignItems = 'center';
      countBox.style.justifyContent = 'space-between';

      const label = document.createElement('span');
      label.style.fontSize = '0.75rem';
      label.style.color = 'var(--text-muted)';
      label.textContent = 'Graph Count Result';

      const val = document.createElement('span');
      val.style.fontFamily = 'var(--font-mono)';
      val.style.fontWeight = '700';
      val.style.color = 'var(--accent-secondary)';
      val.textContent = `${result.count} rows`;

      countBox.appendChild(label);
      countBox.appendChild(val);
      container.appendChild(countBox);
      return container;
    }

    // 2. Tabular row records array
    const isArrayOfObjects = Array.isArray(result) && result.length > 0 && typeof result[0] === 'object';

    if (isArrayOfObjects) {
      const headerRow = document.createElement('div');
      headerRow.className = 'result-tabs-row';

      const tag = document.createElement('span');
      tag.className = 'result-tag';
      tag.textContent = `Neo4j Result (${result.length} records)`;

      const toggleBtns = document.createElement('div');
      toggleBtns.className = 'view-toggle-btns';

      const tableBtn = document.createElement('button');
      tableBtn.className = 'toggle-btn active';
      tableBtn.textContent = 'Table';

      const jsonBtn = document.createElement('button');
      jsonBtn.className = 'toggle-btn';
      jsonBtn.textContent = 'JSON';

      toggleBtns.appendChild(tableBtn);
      toggleBtns.appendChild(jsonBtn);
      headerRow.appendChild(tag);
      headerRow.appendChild(toggleBtns);
      container.appendChild(headerRow);

      // Table View
      const tableWrapper = document.createElement('div');
      tableWrapper.className = 'result-table-wrapper';

      const table = document.createElement('table');
      table.className = 'result-table';

      // Collect all keys across rows
      const allKeys = Array.from(new Set(result.flatMap(r => Object.keys(r))));

      const thead = document.createElement('thead');
      const trHead = document.createElement('tr');
      allKeys.forEach(k => {
        const th = document.createElement('th');
        th.textContent = k;
        trHead.appendChild(th);
      });
      thead.appendChild(trHead);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      result.forEach(row => {
        const tr = document.createElement('tr');
        allKeys.forEach(k => {
          const td = document.createElement('td');
          const val = row[k];
          td.textContent = (typeof val === 'object' && val !== null) ? JSON.stringify(val) : (val !== undefined ? val : '');
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      tableWrapper.appendChild(table);

      // JSON View (hidden by default)
      const jsonView = document.createElement('pre');
      jsonView.className = 'result-json-view';
      jsonView.style.display = 'none';
      jsonView.textContent = JSON.stringify(result, null, 2);

      tableBtn.addEventListener('click', () => {
        tableBtn.classList.add('active');
        jsonBtn.classList.remove('active');
        tableWrapper.style.display = 'block';
        jsonView.style.display = 'none';
      });

      jsonBtn.addEventListener('click', () => {
        jsonBtn.classList.add('active');
        tableBtn.classList.remove('active');
        tableWrapper.style.display = 'none';
        jsonView.style.display = 'block';
      });

      container.appendChild(tableWrapper);
      container.appendChild(jsonView);
      return container;
    }

    // 3. Fallback generic JSON view
    const jsonView = document.createElement('pre');
    jsonView.className = 'result-json-view';
    jsonView.textContent = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
    container.appendChild(jsonView);
    return container;
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ResultRenderer };
} else {
  window.ResultRenderer = ResultRenderer;
}
