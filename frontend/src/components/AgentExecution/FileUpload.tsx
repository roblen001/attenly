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

  // Cancel a specific file upload
  const cancelFileUpload = (fileId: string) => {
    const fileToCancel = files.find(f => f.id === fileId);
    if (fileToCancel?.abortController) {
      fileToCancel.abortController.abort();
      
      // Remove cancelled file from UI immediately
      const updatedFiles = files.filter(f => f.id !== fileId);
      onFilesChange(updatedFiles);
    }
  };

  // Cancel all pending uploads
  const cancelAllUploads = () => {
    // Abort all uploading/queued files and remove them from UI
    const filesToKeep = files.filter(file => {
      if (file.status === 'uploading' || file.status === 'queued') {
        if (file.abortController) {
          file.abortController.abort();
        }
        return false; // Remove from UI
      }
      return true; // Keep completed/failed files
    });
    onFilesChange(filesToKeep);
    setUploading(false);
  };

  // checks if the there was a change in the file input
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    setUploading(true);
    setError(null);

    // Convert FileList to Array for easier manipulation
    const fileArray = Array.from(selectedFiles);
    
    // Create initial files with queue positions and AbortControllers
    const initialFiles: UploadedFile[] = fileArray.map((file, index) => ({
      id: `temp-${Date.now()}-${index}`, // Temporary ID until we get real one from backend
      name: file.name,
      size: file.size,
      type: file.type || 'application/pdf',
      status: index === 0 ? 'uploading' as const : 'queued' as const,
      queuePosition: index + 1,
      abortController: new AbortController(),
      progress: 0
    }));
    
    // Add files to UI immediately
    let currentFiles = [...files, ...initialFiles];
    onFilesChange(currentFiles);
    
    // Process files sequentially
    const processedFiles: UploadedFile[] = [];
    let hasErrors = false;
    
    for (let i = 0; i < fileArray.length; i++) {
      const file = fileArray[i];
      const tempFile = initialFiles[i];
      
      // Check if this file was cancelled (removed from UI) before we started processing it
      const currentFileState = currentFiles.find(f => f.id === tempFile.id);
      if (!currentFileState) {
        // File was cancelled and removed from UI, skip processing
        continue;
      }
      
      // Update file status to uploading if it was queued
      if (tempFile.status === 'queued') {
        currentFiles = currentFiles.map(f => 
          f.id === tempFile.id ? { ...f, status: 'uploading' as const } : f
        );
        onFilesChange(currentFiles);
      }
      
      try {
        // Create FormData for single file upload
        const formData = new FormData();
        formData.append('files', file);
        
        // Upload single file to backend with AbortController
        const response = await api('/agents/files/upload', {
          method: 'POST',
          body: formData,
          signal: tempFile.abortController?.signal
        });

        const result = await response.json();
        
        if (result.files && result.files.length > 0) {
          const uploadedFile = result.files[0]; // Should be only one file
          // Preserve the AbortController reference (though upload is complete)
          uploadedFile.abortController = tempFile.abortController;
          processedFiles.push(uploadedFile);
          
          // Update the specific file in the UI
          currentFiles = currentFiles.map(f => 
            f.id === tempFile.id ? uploadedFile : f
          );
          onFilesChange(currentFiles);
          
          // Check for issues with this file
          if (uploadedFile.status === 'failed' || uploadedFile.status === 'duplicate') {
            hasErrors = true;
          }
        } else {
          // Handle case where no files were returned
          const failedFile: UploadedFile = {
            ...tempFile,
            status: 'failed',
            error: 'No response from server'
          };
          processedFiles.push(failedFile);
          
          currentFiles = currentFiles.map(f => 
            f.id === tempFile.id ? failedFile : f
          );
          onFilesChange(currentFiles);
          hasErrors = true;
        }
        
      } catch (err) {
        // Check if the error was due to abortion
        if (err instanceof Error && err.name === 'AbortError') {
          // File was cancelled - remove it completely from UI, don't add to processedFiles
          currentFiles = currentFiles.filter(f => f.id !== tempFile.id);
          onFilesChange(currentFiles);
          // Don't add cancelled files to processedFiles or show them in summary
        } else {
          // Handle other upload failures
          let errorMessage = 'Upload failed';
          
          if (err instanceof Error) {
            // Check if it's an authentication error
            if (err.message.includes('Authentication failed')) {
              errorMessage = 'Session expired - please refresh the page and log in again';
            } else {
              errorMessage = err.message;
            }
          }
          
          const failedFile: UploadedFile = {
            ...tempFile,
            status: 'failed',
            error: errorMessage
          };
          processedFiles.push(failedFile);
          
          currentFiles = currentFiles.map(f => 
            f.id === tempFile.id ? failedFile : f
          );
          onFilesChange(currentFiles);
          hasErrors = true;
        }
      }
    }
    
    // Show summary message if there were any issues
    if (hasErrors) {
      const successful = processedFiles.filter(f => f.status === 'uploaded').length;
      const failed = processedFiles.filter(f => f.status === 'failed').length;
      const duplicates = processedFiles.filter(f => f.status === 'duplicate').length;
      
      const message = `Processed ${processedFiles.length} files: `;
      const parts = [];
      if (successful > 0) parts.push(`${successful} successful`);
      if (failed > 0) parts.push(`${failed} failed`);
      if (duplicates > 0) parts.push(`${duplicates} duplicates`);
      
      setError(message + parts.join(', '));
      
      // Clear error after a few seconds
      setTimeout(() => setError(null), 5000);
    }
    
    // Clear the input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    
    setUploading(false);
  };

  const removeFile = async (fileId: string) => {
    try {
      await api(`/agents/files/${fileId}`, {
        method: 'DELETE',
      });
    } catch (err) {
      // If file not found (404), it's already gone - that's fine
      const errorMessage = err instanceof Error ? err.message : 'Delete failed';
      if (!errorMessage.includes('404') && !errorMessage.includes('not found')) {
        setError(errorMessage);
        return; // Don't remove from UI if it's a real error
      }
    }
    
    // Remove file from UI (whether delete succeeded or file was already gone)
    const updatedFiles = files.filter(file => file.id !== fileId);
    onFilesChange(updatedFiles);
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

  const getStatusIcon = (status: string, queuePosition?: number) => {
    switch (status) {
      case 'queued':
        return (
          <span style={{ color: '#6b7280' }} title={`Queued (position ${queuePosition})`}>
            #{queuePosition}
          </span>
        );
      case 'uploading':
        return (
          <span style={{ 
            display: 'inline-block',
            animation: 'spin 1s linear infinite'
          }}>
            ⏳
          </span>
        );
      case 'uploaded':
        return '✅';
      case 'failed':
        return '❌';
      case 'duplicate':
        return '🔄';
      default:
        return '📄';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'queued':
        return '#9ca3af';
      case 'uploading':
        return '#6b7280';
      case 'uploaded':
        return '#10b981';
      case 'failed':
        return '#ef4444';
      case 'duplicate':
        return '#f59e0b';
      default:
        return '#6b7280';
    }
  };

  const getActionButton = (file: UploadedFile) => {
    if (file.status === 'uploading' || file.status === 'queued') {
      return (
        <button
          onClick={() => cancelFileUpload(file.id)}
          className="remove-file-btn-compact"
          title="Cancel upload"
          style={{ backgroundColor: '#ef4444', color: 'white' }}
        >
          ⏹️
        </button>
      );
    } else {
      return (
        <button
          onClick={() => removeFile(file.id)}
          className="remove-file-btn-compact"
          title="Remove file"
          disabled={false}
        >
          ✕
        </button>
      );
    }
  };

  return (
    <div className="file-upload-section">
      <div className="section-header">
        <h4>PDF Documents</h4>
        <div style={{ display: 'flex', gap: '8px' }}>
          {uploading && (
            <button 
              onClick={cancelAllUploads}
              className="btn"
              style={{ 
                fontSize: '0.8rem', 
                padding: '6px 12px',
                backgroundColor: '#ef4444',
                color: 'white',
                border: '1px solid #ef4444'
              }}
            >
              ⏹️ Cancel All
            </button>
          )}
          <button 
            onClick={() => fileInputRef.current?.click()}
            className="btn btn-primary"
            style={{ fontSize: '0.8rem', padding: '6px 12px' }}
            disabled={uploading}
          >
            {uploading ? '⏳ Uploading...' : '📁 Upload PDFs'}
          </button>
        </div>
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
                title={
                  file.status === 'failed' && file.error 
                    ? `Failed: ${file.error}`
                    : file.status === 'duplicate' && file.error
                    ? `Duplicate: ${file.error}`
                    : file.status === 'uploaded'
                    ? 'Successfully uploaded and processed'
                    : file.status === 'queued'
                    ? `Queued for upload (position ${file.queuePosition})`
                    : file.status === 'uploading'
                    ? 'Currently uploading...'
                    : file.status
                }
              >
                {getStatusIcon(file.status, file.queuePosition)}
              </span>
              <span 
                className='file-name-compact'
                title={
                  file.error 
                    ? `${file.name} - ${file.error}`
                    : file.name
                }
                style={{
                  color: file.status === 'failed' ? '#ef4444' : 
                         file.status === 'duplicate' ? '#f59e0b' : 'inherit'
                }}
              >
                {truncateFileName(file.name)}
              </span>
              <span className="file-size-compact">{formatFileSize(file.size)}</span>
              {getActionButton(file)}
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
