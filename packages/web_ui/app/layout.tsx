import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Solamon Energy Assessment",
  description: "Live energy assessment and reporting portal"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
