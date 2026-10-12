"use client";
import { useEffect } from "react";
import { refreshSession } from "@/store/api";
import { sessionStarted, signedOut } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/** On first load the token is gone (memory only); the refresh cookie brings the session back. */
export function useSessionBoot() {
  const dispatch = useAppDispatch();
  const status = useAppSelector((s) => s.auth.status);
  useEffect(() => {
    if (status !== "unknown") return;
    refreshSession().then((s) => dispatch(s ? sessionStarted(s) : signedOut()));
  }, [status, dispatch]);
  return status;
}
