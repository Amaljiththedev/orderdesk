import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { Providers } from "@/store/provider";
import "./globals.css";

// self-hosted fonts (the geist package), so builds and dev work without reaching Google Fonts
export const metadata: Metadata = {
  title: "OrderDesk",
  description: "AI order intake: messy emails and PDFs in, checked and priced orders out.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}>
      <body className="min-h-full bg-white text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
