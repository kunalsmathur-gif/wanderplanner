import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { MobileWarningBanner } from "@/components/common/MobileWarningBanner";
import { ChatBubble } from "@/components/chat/ChatBubble";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });

export const metadata: Metadata = {
  title: "WanderPlan — AI Travel Advisor",
  description:
    "Plan group trips with AI-powered, personalised itineraries. No sign-up required.",
  themeColor: "#1E40AF",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${geist.variable} h-full`}>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1" />
      </head>
      <body className="h-full bg-white text-slate-900 antialiased min-w-[320px]">
        <MobileWarningBanner />
        {children}
        {/* Travel assistant chatbot — visible on all pages */}
        <ChatBubble />
      </body>
    </html>
  );
}
