import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });

export const metadata: Metadata = {
  title: "WanderPlan — AI Travel Advisor",
  description:
    "Plan group trips with AI-powered, personalised itineraries. No sign-up required.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${geist.variable} h-full`}>
      <body className="h-full bg-white text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
