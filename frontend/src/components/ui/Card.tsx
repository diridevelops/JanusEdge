interface CardProps {
  children: React.ReactNode;
  className?: string;
}

/** Simple card wrapper with shadow and rounded corners. */
export function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`card p-6 ${className}`}>
      {children}
    </div>
  );
}
