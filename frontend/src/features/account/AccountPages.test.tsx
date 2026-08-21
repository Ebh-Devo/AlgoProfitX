import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";

import { CreatorEnrollPage } from "./AccountPages";

const enrollCreator = vi.hoisted(() => vi.fn());
const auth = vi.hoisted(() => ({ value: { user: { roles: ["INVESTOR"] }, enrollCreator } }));
vi.mock("../../auth/auth-context", () => ({ useAuth: () => auth.value }));

describe("CreatorEnrollPage", () => {
  it("enrolls an Investor as a Creator", async () => {
    enrollCreator.mockResolvedValue({ roles: ["INVESTOR", "CREATOR"] });
    render(<CreatorEnrollPage />);
    await userEvent.click(screen.getByRole("button", { name: "Enroll as Creator" }));
    expect(enrollCreator).toHaveBeenCalledOnce();
    expect(await screen.findByText("Your account has the Creator role.")).toBeInTheDocument();
  });
});
