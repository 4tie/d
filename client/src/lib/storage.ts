import { useEffect, useState } from "react";

type Setter<T> = T | ((prev: T) => T);
type Initial<T> = T | (() => T);

export function readLocalStorageRaw(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function resolveInitial<T>(initialValue: Initial<T>): T {
  if (typeof initialValue === "function") {
    return (initialValue as () => T)();
  }
  return initialValue;
}

export function useLocalStorageState<T>(key: string, initialValue: Initial<T>) {
  const [value, setValue] = useState<T>(() => {
    const raw = readLocalStorageRaw(key);
    if (raw === null) return resolveInitial(initialValue);
    try {
      return JSON.parse(raw) as T;
    } catch {
      return resolveInitial(initialValue);
    }
  });

  useEffect(() => {
    const raw = readLocalStorageRaw(key);
    if (raw === null) {
      setValue(resolveInitial(initialValue));
      return;
    }
    try {
      setValue(JSON.parse(raw) as T);
    } catch {
      setValue(resolveInitial(initialValue));
    }
  }, [key]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      return;
    }
  }, [key, value]);

  function set(next: Setter<T>) {
    setValue((prev) => {
      if (typeof next === "function") {
        return (next as (p: T) => T)(prev);
      }
      return next;
    });
  }

  return [value, set] as const;
}
