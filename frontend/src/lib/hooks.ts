import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { PublicConfig, Session, Transition } from "./types";

export const useConfig = () => useQuery({ queryKey: ["config"], queryFn: () => api<PublicConfig>("/config"), staleTime: Infinity });

export const useSession = () => useQuery({ queryKey: ["session"], queryFn: () => api<Session | null>("/session") });

export const useTransitions = (enabled = true) =>
  useQuery({ queryKey: ["transitions"], queryFn: () => api<Transition[]>("/transitions"), enabled });

export function useActiveTransition() {
  const q = useTransitions();
  return { ...q, transition: q.data?.find((t) => t.is_active) ?? null };
}

/** Invalidate everything that depends on the workspace's data (after any write). */
export function useRefreshAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ predicate: (q) => !["config"].includes(q.queryKey[0] as string) });
}
