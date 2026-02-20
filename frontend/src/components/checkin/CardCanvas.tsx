interface Props {
  imageUrl: string;
}

/**
 * Displays the annotated image that the backend draws bounding boxes onto.
 * All annotation is done server-side, so this is just a styled <img>.
 */
export function CardCanvas({ imageUrl }: Props) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 overflow-auto max-h-[60vh]">
      <img
        src={imageUrl}
        alt="Annotated card scan"
        className="w-full h-auto object-contain"
      />
    </div>
  );
}

