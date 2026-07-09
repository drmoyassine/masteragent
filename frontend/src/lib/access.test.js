import { canAdministerMemory, visibleSettingsTabs } from "./access";

const tabs = [
  { id: "storage" },
  { id: "memory", adminOnly: true },
];

test("regular users retain prompt settings but not memory administration", () => {
  expect(canAdministerMemory({ is_admin: false })).toBe(false);
  expect(visibleSettingsTabs(tabs, { is_admin: false }).map((tab) => tab.id)).toEqual(["storage"]);
});

test("administrators retain all settings", () => {
  expect(canAdministerMemory({ is_admin: true })).toBe(true);
  expect(visibleSettingsTabs(tabs, { is_admin: true }).map((tab) => tab.id)).toEqual(["storage", "memory"]);
});
