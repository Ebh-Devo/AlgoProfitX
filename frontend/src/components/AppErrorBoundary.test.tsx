import { render, screen } from "@testing-library/react";

import { AppErrorBoundary } from "./AppErrorBoundary";

function BrokenPage(): never { throw new Error("private render stack and token"); }

describe("AppErrorBoundary", () => {
  it("shows branded recovery without internal exception details", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<AppErrorBoundary><BrokenPage /></AppErrorBoundary>);
    expect(screen.getByRole("heading", { name: /couldn’t display this page/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload AlgoProfitX" })).toBeInTheDocument();
    expect(screen.queryByText(/private render stack and token/i)).not.toBeInTheDocument();
  });
});
