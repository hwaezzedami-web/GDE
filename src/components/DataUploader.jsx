import { useState } from 'react';
import { parseCSV, csvToSectionData, CSV_SECTIONS, generateTemplateCSV, detectAndParse } from '../utils/csvParser';
import { useData } from '../context/DataContext';

const DataUploader = ({ onClose }) => {
  const { updateSection, loadedSections } = useData();
  const [results, setResults] = useState({});
  const [autoResult, setAutoResult] = useState(null);

  const handleFile = (sectionKey, file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const rows = parseCSV(e.target.result);
        const parsed = csvToSectionData(sectionKey, rows);
        if (parsed) {
          updateSection(sectionKey, parsed);
          setResults(p => ({ ...p, [sectionKey]: { ok: true, count: rows.length } }));
        } else {
          setResults(p => ({ ...p, [sectionKey]: { ok: false, msg: 'Parse error' } }));
        }
      } catch (err) {
        setResults(p => ({ ...p, [sectionKey]: { ok: false, msg: err.message } }));
      }
    };
    reader.readAsText(file);
  };

  const handleAutoDetect = (file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const rows = parseCSV(e.target.result);
        const detected = detectAndParse(rows);
        if (detected) {
          let count = 0;
          Object.entries(detected).forEach(([key, val]) => {
            updateSection(key, val);
            count++;
          });
          setAutoResult({ ok: true, msg: `Auto-detected! Loaded ${count} sections from ${rows.length} rows`, file: file.name });
        } else {
          setAutoResult({ ok: false, msg: 'Could not auto-detect format. Use section-specific upload below.' });
        }
      } catch (err) {
        setAutoResult({ ok: false, msg: err.message });
      }
    };
    reader.readAsText(file);
  };

  const downloadTemplate = (key) => {
    const csv = generateTemplateCSV(key);
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${key}_template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="uploader-overlay">
      <div className="uploader-panel">
        <div className="uploader-header">
          <h2>Import CSV Data</h2>
          <button className="btn btn-close" onClick={onClose}>Close</button>
        </div>

        {/* Auto-detect zone */}
        <div className="auto-detect-zone">
          <div className="auto-detect-inner">
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>Quick Import (Auto-Detect)</div>
              <div style={{ fontSize: 11, color: '#777' }}>
                Drop your <code>kpi_all_days.csv</code> or any pipe/comma/tab-delimited file.
                The system detects the format and fills all matching sections automatically.
              </div>
            </div>
            <label className="btn btn-primary" style={{ fontSize: 13, padding: '8px 20px' }}>
              Upload File
              <input type="file" accept=".csv,.txt" hidden onChange={e => e.target.files[0] && handleAutoDetect(e.target.files[0])} />
            </label>
          </div>
          {autoResult && (
            <div className={`auto-result ${autoResult.ok ? 'ok' : 'err'}`}>
              {autoResult.ok ? '✓' : '✗'} {autoResult.msg}
            </div>
          )}
        </div>

        <p className="uploader-hint">Or upload individual CSV files per section:</p>
        <div className="uploader-grid">
          {CSV_SECTIONS.map(s => {
            const r = results[s.key];
            const loaded = loadedSections.has(s.key);
            return (
              <div className={`upload-item ${loaded ? 'loaded' : ''}`} key={s.key}>
                <div className="upload-item-info">
                  <div className="upload-item-label">{s.label}</div>
                  <div className="upload-item-cols">{s.desc}</div>
                </div>
                <div className="upload-item-actions">
                  <button className="btn btn-sm" onClick={() => downloadTemplate(s.key)}>Template</button>
                  <label className="btn btn-sm btn-primary">
                    Upload
                    <input type="file" accept=".csv,.txt" hidden onChange={e => e.target.files[0] && handleFile(s.key, e.target.files[0])} />
                  </label>
                  {r && (
                    <span className={`upload-status ${r.ok ? 'ok' : 'err'}`}>
                      {r.ok ? `${r.count} rows` : r.msg}
                    </span>
                  )}
                  {loaded && !r && <span className="upload-status ok">Loaded</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default DataUploader;
