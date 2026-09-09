import { useCallback, useRef, useState } from "react";

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".jpg", ".jpeg", ".png"];

function isAccepted(filename) {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

// Recursively walks a dropped FileSystemEntry tree (drag-and-drop of a folder
// gives you entries, not File objects directly — this flattens it back down
// to a plain File[] the same way a <input webkitdirectory> selection does).
function readEntry(entry) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file(
        (file) => resolve(isAccepted(file.name) ? [file] : []),
        () => resolve([])
      );
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const allEntries = [];
      const readBatch = () => {
        reader.readEntries(async (batch) => {
          if (batch.length === 0) {
            const nested = await Promise.all(allEntries.map(readEntry));
            resolve(nested.flat());
            return;
          }
          allEntries.push(...batch);
          readBatch(); // readEntries only returns a batch at a time — keep going until empty
        }, () => resolve([]));
      };
      readBatch();
    } else {
      resolve([]);
    }
  });
}

async function filesFromDataTransfer(dataTransfer) {
  const items = Array.from(dataTransfer.items || []);
  const entries = items
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
    .filter(Boolean);

  if (entries.length > 0) {
    const nested = await Promise.all(entries.map(readEntry));
    return nested.flat();
  }

  // Fallback for browsers without the entries API — flat file drop only.
  return Array.from(dataTransfer.files || []).filter((f) => isAccepted(f.name));
}

export default function FilePicker({ files, onFilesChange }) {
  const [dragActive, setDragActive] = useState(false);
  const folderInputRef = useRef(null);
  const fileInputRef = useRef(null);

  const addFiles = useCallback((newFiles) => {
    if (newFiles.length === 0) return;
    onFilesChange((prev) => {
      const existingKeys = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const deduped = newFiles.filter((f) => !existingKeys.has(`${f.name}:${f.size}`));
      return [...prev, ...deduped];
    });
  }, [onFilesChange]);

  const onDrop = useCallback(async (e) => {
    e.preventDefault();
    setDragActive(false);
    const dropped = await filesFromDataTransfer(e.dataTransfer);
    addFiles(dropped);
  }, [addFiles]);

  const onFolderSelect = (e) => {
    const selected = Array.from(e.target.files || []).filter((f) => isAccepted(f.name));
    addFiles(selected);
    e.target.value = ""; // allow re-selecting the same folder later
  };

  const onFileSelect = (e) => {
    const selected = Array.from(e.target.files || []).filter((f) => isAccepted(f.name));
    addFiles(selected);
    e.target.value = "";
  };

  const removeFile = (index) => {
    onFilesChange((prev) => prev.filter((_, i) => i !== index));
  };

  const totalSize = files.reduce((sum, f) => sum + f.size, 0);
  const totalSizeLabel = totalSize > 1024 * 1024
    ? `${(totalSize / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(totalSize / 1024))} KB`;

  return (
    <div>
      <div
        className={`file-drop-zone${dragActive ? " drag-active" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
      >
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 4v11m0 0-4-4m4 4 4-4M5 17v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <p className="file-drop-headline">Drag and drop papers or a folder here</p>
        <p className="muted">PDF, DOCX, JPG, PNG</p>

        <div className="file-drop-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => folderInputRef.current?.click()}>
            Select folder
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()}>
            Select files
          </button>
        </div>

        {/* webkitdirectory triggers the browser's native folder picker — supported in Chrome, Edge, Firefox, Safari */}
        <input
          ref={folderInputRef}
          type="file"
          webkitdirectory=""
          directory=""
          multiple
          hidden
          onChange={onFolderSelect}
        />
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          hidden
          onChange={onFileSelect}
        />
      </div>

      {files.length > 0 && (
        <div className="file-picker-summary">
          <div className="file-picker-summary-head">
            <span>{files.length} file{files.length === 1 ? "" : "s"} selected · {totalSizeLabel}</span>
            <button type="button" className="link-btn" onClick={() => onFilesChange([])}>Clear all</button>
          </div>
          <ul className="file-picker-list">
            {files.slice(0, 8).map((f, i) => (
              <li key={`${f.name}-${f.size}-${i}`}>
                <span className="file-picker-name">{f.name}</span>
                <button type="button" className="icon-btn file-picker-remove" onClick={() => removeFile(i)} aria-label="Remove">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                </button>
              </li>
            ))}
            {files.length > 8 && <li className="muted">…and {files.length - 8} more</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
