import { Link } from 'react-router-dom';

/** 404 page component. */
export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center">
      <h1 className="text-6xl font-bold text-gray-300 dark:text-gray-600">404</h1>
      <p className="mt-4 text-lg text-gray-500 dark:text-gray-400">Page not found</p>
      <Link to="/" className="btn-primary mt-6">
        Go to Dashboard
      </Link>
    </div>
  );
}
