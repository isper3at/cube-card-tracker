import { useRef, useState } from 'react';

interface Props {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

export function ImageUpload({ onFileSelected, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFile(file: File) {
    if (file.type.startsWith('image/')) {
      onFileSelected(file);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={[
        'border-2 border-dashed rounded-xl p-12 text-center transition-colors',
        dragging
          ? 'border-blue-500 bg-blue-50'
          : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
      ].join(' ')}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          // Reset so the same file can be re-selected if needed
          e.target.value = '';
        }}
      />
      <div className="text-4xl mb-3">📸</div>
      <p className="text-gray-700 font-medium">Drop an image here, or click to browse</p>
      <p className="text-gray-400 text-sm mt-1">JPEG · PNG · WEBP</p>
    </div>
  );
}

