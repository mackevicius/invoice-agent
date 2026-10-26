import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { LoaderCircle, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ApiError, DemoCompanyExpiredError } from '@/lib/api';
import { uploadInvoice, type InvoiceDetail } from './api';
import styles from './split-view.module.css';

const contentTypes = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
];

export function UploadInvoice({
  onUploaded,
  onCancel,
  onExpired,
}: {
  onUploaded: (invoice: InvoiceDetail) => void;
  onCancel: () => void;
  onExpired: (error: DemoCompanyExpiredError) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const upload = useMutation({
    mutationFn: uploadInvoice,
    onSuccess: onUploaded,
    onError: (error) => {
      if (error instanceof DemoCompanyExpiredError) onExpired(error);
    },
  });

  function selectFile(selected: File | undefined) {
    if (!selected || upload.isPending) return;
    upload.reset();
    setFile(null);
    if (!contentTypes.includes(selected.type)) {
      setFileError('Choose a PDF, PNG, JPEG, WebP, or GIF file.');
    } else if (selected.size === 0) {
      setFileError('Choose a non-empty file.');
    } else if (selected.size > 10 * 1024 * 1024) {
      setFileError('Invoice files must be 10 MB or smaller.');
    } else {
      setFileError(null);
      setFile(selected);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (file && !upload.isPending) upload.mutate(file);
  }

  const error =
    fileError ??
    (upload.error instanceof ApiError
      ? upload.error.message
      : upload.error
        ? 'Unable to upload this Invoice. Please try again.'
        : null);

  return (
    <section className={styles.uploadPage}>
      <header className={styles.uploadHeading}>
        <h1>Upload Invoice</h1>
        <Button variant="ghost" onClick={onCancel} disabled={upload.isPending}>
          <X aria-hidden="true" /> Cancel
        </Button>
      </header>
      <form onSubmit={submit} aria-busy={upload.isPending}>
        <label
          htmlFor="invoice-file"
          className={`${styles.dropZone} ${dragging ? styles.dragging : ''}`}
          onDragOver={(event) => {
            event.preventDefault();
            if (!upload.isPending) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (upload.isPending) return;
            if (event.dataTransfer.files.length !== 1) {
              upload.reset();
              setFile(null);
              setFileError('Choose one Invoice file at a time.');
              return;
            }
            selectFile(event.dataTransfer.files[0]);
          }}
        >
          <Upload aria-hidden="true" size={28} />
          <strong>{file?.name ?? 'Invoice file'}</strong>
          <span>PDF, PNG, JPEG, WebP or GIF. 10 MB maximum.</span>
          <input
            id="invoice-file"
            type="file"
            aria-label="Invoice file"
            accept={contentTypes.join(',')}
            disabled={upload.isPending}
            onChange={(event) => selectFile(event.target.files?.[0])}
          />
        </label>
        {error && (
          <p className={styles.uploadError} role="alert">
            {error}
          </p>
        )}
        <div className={styles.uploadActions}>
          <Button type="submit" disabled={file === null || upload.isPending}>
            {upload.isPending ? (
              <LoaderCircle aria-hidden="true" className={styles.spin} />
            ) : (
              <Upload aria-hidden="true" />
            )}
            {upload.isPending ? 'Uploading Invoice' : 'Upload Invoice'}
          </Button>
        </div>
      </form>
    </section>
  );
}
