import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Solamon POC",
  description: "Solar Monitor operations dashboard POC"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
