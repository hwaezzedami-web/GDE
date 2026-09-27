import { useState, useRef } from 'react';
import { parseCSV, csvToSectionData, CSV_SECTIONS, generateTemplateCSV } from '../utils/csvParser';
import { useData } from '../context/DataContext';

const DataUploader = ({ onClose }) => {
  const { updateSection, loadedSections } = useData();
  const [results, setResults] = useState({});
  const fileRef = useRef();

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

  const downloadAll = () => {
    CSV_SECTIONS.forEach(s => downloadTemplate(s.key));
  };

  return (
    <div className="uploader-overlay">
      <div className="uploader-panel">
        <div className="uploader-header">
          <h2>Import CSV Data</h2>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-outline" onClick={downloadAll}>Download All Templates</button>
            <button className="btn btn-close" onClick={onClose}>Close</button>
          </div>
        </div>
        <p className="uploader-hint">Upload CSV files for each section. Click "Template" to download a sample CSV with the correct headers.</p>
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
