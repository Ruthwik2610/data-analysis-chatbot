import { render } from "@testing-library/react";
import { WebVitalsReporter } from "@/app/WebVitalsReporter";

vi.mock("next/web-vitals", () => ({
  useReportWebVitals: (callback: (metric: { name: string; value: number }) => void) => {
    callback({ name: "INP", value: 120 });
  },
}));

describe("WebVitalsReporter", () => {
  it("reports web vitals through the provided callback", () => {
    const onMetric = vi.fn();

    render(<WebVitalsReporter onMetric={onMetric} />);

    expect(onMetric).toHaveBeenCalledWith({ name: "INP", value: 120 });
  });
});
