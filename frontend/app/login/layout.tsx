"use client";
import { useSessionBoot } from "@/components/session";

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  useSessionBoot();   // already signed in (cookie)? the page sends you on to the inbox
  return children;
}
