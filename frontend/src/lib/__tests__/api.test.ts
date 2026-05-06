import { api } from "../api";

describe("api.listChats", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("requests project scoped recents", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    await api.listChats("proj_1");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/chats?project_id=proj_1",
      expect.any(Object),
    );
  });

  it("requests unscoped recents when no project is active", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    await api.listChats(null);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/chats?project_id=none",
      expect.any(Object),
    );
  });
});
