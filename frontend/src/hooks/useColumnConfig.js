import { useState, useCallback } from "react";

/**
 * Manage per-table column visibility + ordering, persisted to localStorage
 * under "me-cols-${tableKey}".
 *
 * @param {Record<string, Array<{key: string, label: string, fixed?: boolean}>>} columnDefs
 *   Map of tableKey → default column definitions.
 * @returns {{
 *   colCfg, setColCfg, toggleCol, moveCol, visCols
 * }}
 */
export function useColumnConfig(columnDefs) {
  const loadColCfg = (tableKey) => {
    const defaults = columnDefs[tableKey];
    try {
      const saved = localStorage.getItem(`me-cols-${tableKey}`);
      if (saved) {
        const parsed = JSON.parse(saved);
        const savedKeys = parsed.map((c) => c.key);
        const merged = parsed.filter((c) => defaults.some((d) => d.key === c.key));
        defaults.forEach((d) => {
          if (!savedKeys.includes(d.key)) merged.push({ ...d, visible: true });
        });
        return merged;
      }
    } catch {
      /* ignore */
    }
    return defaults.map((c) => ({ ...c, visible: true }));
  };

  const [colCfg, setColCfg] = useState(() => {
    const initial = {};
    for (const k of Object.keys(columnDefs)) initial[k] = loadColCfg(k);
    return initial;
  });

  const toggleCol = useCallback((tableKey, key) => {
    setColCfg((prev) => {
      const updated = {
        ...prev,
        [tableKey]: prev[tableKey].map((c) =>
          c.key === key ? { ...c, visible: !c.visible } : c
        ),
      };
      localStorage.setItem(`me-cols-${tableKey}`, JSON.stringify(updated[tableKey]));
      return updated;
    });
  }, []);

  const moveCol = useCallback((tableKey, key, dir) => {
    setColCfg((prev) => {
      const arr = [...prev[tableKey]];
      const idx = arr.findIndex((c) => c.key === key);
      if (idx < 0) return prev;
      const t = idx + dir;
      if (t < 0 || t >= arr.length) return prev;
      [arr[idx], arr[t]] = [arr[t], arr[idx]];
      const updated = { ...prev, [tableKey]: arr };
      localStorage.setItem(`me-cols-${tableKey}`, JSON.stringify(arr));
      return updated;
    });
  }, []);

  const visCols = useCallback(
    (tableKey) => colCfg[tableKey].filter((c) => c.visible || c.fixed),
    [colCfg]
  );

  return { colCfg, setColCfg, toggleCol, moveCol, visCols };
}
