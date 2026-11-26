import type { Metadata } from "next";
import { ConverterApp } from "@/components/converter/converter-app";

export const metadata: Metadata = {
  title: "Converter | Parquet to CSV Converter",
};

export default function ConvertPage() {
  return <ConverterApp />;
}
