"use client";
import { useState } from "react";
import { Provider } from "react-redux";
import { ToastProvider } from "@/components/ui/toast";
import { makeStore } from "./index";

export function Providers({ children }: { children: React.ReactNode }) {
  const [store] = useState(makeStore);   // one store per browser tab
  return (
    <Provider store={store}>
      <ToastProvider>{children}</ToastProvider>
    </Provider>
  );
}
