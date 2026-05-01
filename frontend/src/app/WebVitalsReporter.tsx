"use client";

import { useReportWebVitals } from "next/web-vitals";

interface WebMetric {
  name: string;
  value: number;
  id?: string;
  rating?: string;
}

interface WebVitalsReporterProps {
  onMetric?: (metric: WebMetric) => void;
}

export function WebVitalsReporter({ onMetric }: WebVitalsReporterProps) {
  useReportWebVitals((metric) => {
    if (onMetric) {
      onMetric(metric);
      return;
    }
    if (process.env.NODE_ENV === "production") {
      console.info("[web-vital]", metric.name, metric.value, metric.rating);
    }
  });

  return null;
}
