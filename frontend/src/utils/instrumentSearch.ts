/** Remove case and separator differences from instrument identifiers. */
export function normalizeInstrumentSearch(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, '');
}

/** Match a normalized query as a contiguous substring of any supplied field. */
export function matchesInstrumentSearch(
  searchableValues: readonly string[],
  query: string
): boolean {
  const normalizedQuery = normalizeInstrumentSearch(query);
  return matchesNormalizedInstrumentSearch(searchableValues, normalizedQuery);
}

function matchesNormalizedInstrumentSearch(
  searchableValues: readonly string[],
  normalizedQuery: string
): boolean {
  if (!normalizedQuery) return true;

  return searchableValues.some((value) => (
    normalizeInstrumentSearch(value).includes(normalizedQuery)
  ));
}

/** Filter in source order so matching does not disturb catalog/table ordering. */
export function filterInstrumentSearch<T>(
  items: readonly T[],
  query: string,
  getSearchableValues: (item: T) => readonly string[]
): T[] {
  const normalizedQuery = normalizeInstrumentSearch(query);
  if (!normalizedQuery) return [...items];

  return items.filter((item) => matchesNormalizedInstrumentSearch(
    getSearchableValues(item),
    normalizedQuery
  ));
}
