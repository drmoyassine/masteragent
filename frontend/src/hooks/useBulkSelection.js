import { useState, useCallback } from "react";

/**
 * Manage a set of selected row IDs over a list of items.
 * Returns stable callbacks; safe to use as deps.
 */
export function useBulkSelection(items) {
  const [selectedIds, setSelectedIds] = useState([]);

  const toggleAll = useCallback((checked) => {
    if (checked) setSelectedIds(items.map((it) => it.id));
    else setSelectedIds([]);
  }, [items]);

  const toggleOne = useCallback((id) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }, []);

  const clear = useCallback(() => setSelectedIds([]), []);

  return { selectedIds, toggleAll, toggleOne, clear };
}
