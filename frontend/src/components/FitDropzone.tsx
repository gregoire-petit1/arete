import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Upload, FileUp, Check, X, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface UploadResult {
  filename: string;
  status: 'success' | 'error' | 'uploading';
  message?: string;
}

interface FitDropzoneProps {
  onUpload: (file: File) => Promise<void>;
  isUploading?: boolean;
  recentUploads?: UploadResult[];
}

export function FitDropzone({ onUpload, isUploading = false, recentUploads = [] }: FitDropzoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);

  const handleDrop = useCallback(
    async (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragOver(false);
      
      const files = Array.from(e.dataTransfer.files);
      const fitFiles = files.filter(f => f.name.toLowerCase().endsWith('.fit'));
      
      for (const file of fitFiles) {
        await onUpload(file);
      }
    },
    [onUpload]
  );

  const handleFileInput = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      for (const file of files) {
        await onUpload(file);
      }
      e.target.value = '';
    },
    [onUpload]
  );

  return (
    <div className="space-y-4">
      {/* Dropzone */}
      <motion.div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        animate={isDragOver ? { scale: 1.02 } : { scale: 1 }}
        className={cn(
          'relative border-2 border-dashed rounded-lg p-8 text-center',
          'transition-all duration-200 cursor-pointer',
          isDragOver
            ? 'border-neon-cyan bg-neon-cyan/10'
            : 'border-text-muted/30 hover:border-neon-cyan/50 hover:bg-abyss/50'
        )}
      >
        <input
          type="file"
          accept=".fit"
          multiple
          onChange={handleFileInput}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          disabled={isUploading}
        />
        
        <div className="flex flex-col items-center gap-3">
          {isUploading ? (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            >
              <Loader2 className="w-8 h-8 text-neon-cyan" />
            </motion.div>
          ) : (
            <motion.div
              animate={isDragOver ? { y: -5 } : { y: 0 }}
            >
              <Upload className={cn(
                'w-8 h-8',
                isDragOver ? 'text-neon-cyan' : 'text-text-muted'
              )} />
            </motion.div>
          )}
          
          <div>
            <span className={cn(
              'text-sm font-mono',
              isDragOver ? 'text-neon-cyan' : 'text-text-muted'
            )}>
              {isUploading ? 'UPLOADING...' : '⬆️ DRAG & DROP .FIT FILE HERE'}
            </span>
            <div className="text-xs text-text-muted/70 mt-1">
              or click to browse
            </div>
          </div>
        </div>
      </motion.div>

      {/* Recent uploads */}
      {recentUploads.length > 0 && (
        <div className="space-y-2">
          <span className="text-xs font-mono text-text-muted">Recent uploads:</span>
          {recentUploads.map((upload, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 text-xs font-mono"
            >
              <FileUp className="w-3 h-3 text-text-muted" />
              <span className="text-text-secondary">{upload.filename}</span>
              <span className="text-text-muted">→</span>
              {upload.status === 'uploading' && (
                <Loader2 className="w-3 h-3 text-neon-cyan animate-spin" />
              )}
              {upload.status === 'success' && (
                <>
                  <Check className="w-3 h-3 text-success-green" />
                  <span className="text-success-green">{upload.message || 'Parsed'}</span>
                </>
              )}
              {upload.status === 'error' && (
                <>
                  <X className="w-3 h-3 text-danger-red" />
                  <span className="text-danger-red">{upload.message || 'Failed'}</span>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
