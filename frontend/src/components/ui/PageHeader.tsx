import type { LucideIcon } from 'lucide-react';

interface PageHeaderProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  descriptionClassName?: string;
}

/** Shared page header with sidebar-matched icon treatment. */
export function PageHeader({
//   icon: Icon,
  title,
  description,
  descriptionClassName,
}: PageHeaderProps) {
  return (
    <div>
      <div className="flex items-center gap-2">
        {/* <Icon className="h-6 w-6 text-brand-600" aria-hidden="true" /> */}
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{title}</h1>
      </div>
      {description ? (
        <p className={descriptionClassName ?? 'mt-1 text-sm text-gray-500 dark:text-gray-400'}>
          {description}
        </p>
      ) : null}
    </div>
  );
}