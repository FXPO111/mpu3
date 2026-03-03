import "./globals.css";
import type { Metadata } from "next";
import { Manrope } from "next/font/google";
import PublicMotion from "./_components/PublicMotion";

const manrope = Manrope({
  subsets: ["latin", "cyrillic"],
  variable: "--font-sans",
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "MPU AI",
  description: "MPU AI platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={manrope.variable}>
      <body className="root-body">
        <PublicMotion />
        {children}
      </body>
    </html>
  );
}