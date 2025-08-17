import React, { useRef, useState } from 'react';
import type { UploadedFile } from '../../types';
import { api } from '../../libs/https';
import '../../pages/AgentExecution.css';

interface FileUploadProps {
  files: UploadedFile[];
  onFilesChange: (files: UploadedFile[]) => void;
}

export default function FileUpload({ files, onFilesChange }: FileUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // checks if the there was a change in the file input
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    setUploading(true);
    setError(null);

    try {
      // Create FormData for file upload
      const formData = new FormData();
      for (let i = 0; i < selectedFiles.length; i++) {
        formData.append('files', selectedFiles[i]);
      }

      // Upload files to backend
      const response = await api('/agents/files/upload', {
        method: 'POST',
        headers: {}, // Remove Content-Type to let browser set it for FormData
        body: formData,
      });

      const result = await response.json();
      
      // Add uploaded files to the list
      onFilesChange([...files, ...result.files]);
      
      // Clear the input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const removeFile = async (fileId: string) => {
    try {
      await api(`/agents/files/${fileId}`, {
        method: 'DELETE',
      });

      // Remove file from UI
      const updatedFiles = files.filter(file => file.id !== fileId);
      onFilesChange(updatedFiles);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const truncateFileName = (fileName: string, maxLength: number = 25) => {
    if (fileName.length <= maxLength) return fileName;
    const extension = fileName.split('.').pop();
    const nameWithoutExt = fileName.substring(0, fileName.lastIndexOf('.'));
    const truncatedName = nameWithoutExt.substring(0, maxLength - extension!.length - 4);
    return `${truncatedName}...${extension}`;
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'uploading':
        return '⏳';
      case 'uploaded':
        return '✅';
      case 'failed':
        return '❌';
      default:
        return '📄';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'uploading':
        return '#6b7280';
      case 'uploaded':
        return '#10b981';
      case 'failed':
        return '#ef4444';
      default:
        return '#6b7280';
    }
  };

  return (
    <div className="file-upload-section">
      <div className="section-header">
        <h4>PDF Documents</h4>
        <button 
          onClick={() => fileInputRef.current?.click()}
          className="btn btn-primary"
          style={{ fontSize: '0.8rem', padding: '6px 12px' }}
          disabled={uploading}
        >
          {uploading ? '⏳ Uploading...' : '📁 Upload PDFs'}
        </button>
      </div>
      
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf"
        onChange={handleFileUpload}
        style={{ display: 'none' }}
      />

      {error && (
        <div style={{ 
          color: '#ef4444', 
          fontSize: '0.9rem', 
          marginBottom: '10px',
          padding: '8px',
          backgroundColor: '#fef2f2',
          border: '1px solid #fecaca',
          borderRadius: '4px'
        }}>
          {error}
        </div>
      )}

      {files.length > 0 && (
        <div className="uploaded-files">
          {files.map((file) => (
            <div key={file.id} className="file-item-compact">
              <span 
                className="file-icon-compact"
                style={{ color: getStatusColor(file.status) }}
                title={file.status}
              >
                {getStatusIcon(file.status)}
              </span>
              <span 
                className='file-name-compact'
                title={file.name}
              >
                {truncateFileName(file.name)}
              </span>
              <span className="file-size-compact">{formatFileSize(file.size)}</span>
              <button
                onClick={() => removeFile(file.id)}
                className="remove-file-btn-compact"
                title="Remove file"
                disabled={file.status === 'uploading'}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {files.length === 0 && (
        <div className="no-files">
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem', textAlign: 'center' }}>
            No PDF files uploaded yet. Click "Upload PDFs" to add documents for processing.
          </p>
        </div>
      )}
    </div>
  );
}
