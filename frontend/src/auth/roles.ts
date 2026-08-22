import type { User } from "../api/types";

export const CREATOR_ROLE = "CREATOR";
export const INVESTOR_ROLE = "INVESTOR";

export function hasRole(user: User | null, role: string): boolean {
  return user?.roles.includes(role) ?? false;
}
